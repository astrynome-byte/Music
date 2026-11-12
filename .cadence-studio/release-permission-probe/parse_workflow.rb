#!/usr/bin/env ruby
# SPDX-License-Identifier: GPL-3.0-only
# Parse data only: never ERB, object deserialization, source evaluation or aliases.
require 'json'
require 'yaml'

def checked_mapping_keys(node, depth = 0)
  raise 'YAML depth bound' if depth > 60
  if node.is_a?(Psych::Nodes::Alias)
    raise 'YAML aliases refused'
  elsif node.is_a?(Psych::Nodes::Mapping)
    seen = {}
    node.children.each_slice(2) do |key, value|
      raise 'Only scalar mapping keys permitted' unless key.is_a?(Psych::Nodes::Scalar)
      raise 'Duplicate mapping key refused' if seen.key?(key.value)
      seen[key.value] = true
      checked_mapping_keys(value, depth + 1)
    end
  elsif node.respond_to?(:children) && node.children
    node.children.each { |child| checked_mapping_keys(child, depth + 1) }
  end
end

begin
  raw = STDIN.read(262145)
  raise 'Workflow exceeds 256KiB' if raw.bytesize > 262144
  stream = Psych.parse_stream(raw)
  raise 'Exactly one YAML document required' unless stream.children.size == 1
  mapping = stream.children.first.root
  raise 'Workflow root must be a mapping' unless mapping.is_a?(Psych::Nodes::Mapping)
  checked_mapping_keys(mapping)
  keys = mapping.children.each_slice(2).map { |key, _value| key.value }
  allowed = %w[name run-name on permissions env defaults concurrency jobs]
  raise 'Unknown workflow root key' unless (keys - allowed).empty?
  raise 'Exactly one literal on key required' unless keys.count('on') == 1
  document = YAML.safe_load(raw, permitted_classes: [], permitted_symbols: [], aliases: false)
  raise 'Workflow root must be an object' unless document.is_a?(Hash)
  # Psych YAML1.1 can deserialize literal "on" as boolean true. Accept that
  # precise case only after checking its original AST key, never skip triggers.
  raise 'Ambiguous trigger key' if document.key?('on') && document.key?(true)
  events = document.key?('on') ? document['on'] : document.fetch(true)
  STDOUT.write(JSON.generate({ 'events' => events }))
rescue Exception => error
  # Controlled error category only, no source line / environment / arbitrary data.
  STDERR.write("Workflow YAML data parser refused input (#{error.class}).\n")
  exit 2
end
