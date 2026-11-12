#include <set>
#include <vector>
#include <algorithm>
#include <random>
#include <iostream>
#include <string>
#define TRACEFUNC
struct INavigation { struct Index { int column=-1, row=-1; }; };
enum class MoveDirection { First, Last, Right, Left, Down, Up };
struct Control { std::string name; INavigation::Index idx; bool yes; bool enabled()const{return yes;} const INavigation::Index& index()const{return idx;} };
template<class T>
static T* findNearestEnabled(const std::set<T*>& set, const INavigation::Index& currentIndex, MoveDirection direction)
{
    TRACEFUNC;
    T* ret = nullptr;
    for (T* v : set) {
        if (!v->enabled()) {
            continue;
        }

        switch (direction) {
        case MoveDirection::First: {
            if (!ret) {
                ret = v;
                continue;
            }

            if (v->index().row <= ret->index().row) {
                if (v->index().column <= ret->index().column) {
                    ret = v;
                    continue;
                }
            }
        } break;
        case MoveDirection::Last: {
            if (!ret) {
                ret = v;
                continue;
            }

            if (v->index().row >= ret->index().row) {
                if (v->index().column >= ret->index().column) {
                    ret = v;
                    continue;
                }
            }
        } break;
        case MoveDirection::Right: {
            if (v->index().row != currentIndex.row) {
                continue;
            }

            if (v->index().column > currentIndex.column) {
                if (!ret) {
                    ret = v;
                    continue;
                }

                if (v->index().column < ret->index().column) {
                    ret = v;
                }
            }
        } break;
        case MoveDirection::Left: {
            if (v->index().row != currentIndex.row) {
                continue;
            }

            if (v->index().column < currentIndex.column) {
                if (!ret) {
                    ret = v;
                    continue;
                }

                if (v->index().column > ret->index().column) {
                    ret = v;
                }
            }
        } break;
        case MoveDirection::Down: {
            if (v->index().column != currentIndex.column) {
                continue;
            }

            if (v->index().row > currentIndex.row) {
                if (!ret) {
                    ret = v;
                    continue;
                }

                if (v->index().row < ret->index().row) {
                    ret = v;
                }
            }
        } break;
        case MoveDirection::Up: {
            if (v->index().column != currentIndex.column) {
                continue;
            }

            if (v->index().row < currentIndex.row) {
                if (!ret) {
                    ret = v;
                    continue;
                }

                if (v->index().row > ret->index().row) {
                    ret = v;
                }
            }
        } break;
        }
    }

    return ret;
}

int main(){
  // Explicit QML row/column inventory. Invisible ProgressBar and disabled
  // analysis/save are excluded by enabled() as in the source algorithm.
  const std::vector<Control> inventory={
    {"choose",{-1,0},true},{"tempo",{0,1},true},{"numerator",{1,1},true},
    {"denominator",{2,1},true},{"grid",{0,2},true},{"channel",{1,2},true},
    {"noise",{0,3},true},{"confidence",{1,3},true},{"ack",{-1,4},true},
    {"progress",{-1,5},false},{"close",{0,6},true},
    {"analyze",{1,6},false},{"save",{2,6},false}};
  std::mt19937 random(2008); unsigned checks=0;
  for(unsigned permutation=0;permutation<10000;++permutation){
    auto controls=inventory;std::shuffle(controls.begin(),controls.end(),random);
    std::set<Control*> items;for(auto& c:controls)items.insert(&c);
    auto named=[&](const std::string& n)->Control*{for(auto& c:controls)if(c.name==n)return &c;return nullptr;};
    auto require=[&](Control* got,const std::string& expected,const char* phase){
      ++checks;if(!got||got->name!=expected){std::cerr<<phase<<" expected "<<expected<<" got "<<(got?got->name:"null")<<"\n";std::exit(2);}};
    auto step=[&](const std::string& from,MoveDirection d,const std::string& to){require(findNearestEnabled(items,named(from)->index(),d),to,"arrow");};
    auto pgdown=[&](const std::string& from,const std::string& to){auto index=named(from)->index();index.column=0;require(findNearestEnabled(items,index,MoveDirection::Down),to,"PgDown");};
    // Show the old source mismatch independently of the patched route.
    step("choose",MoveDirection::Down,"ack");
    pgdown("choose","tempo");step("tempo",MoveDirection::Down,"grid");step("grid",MoveDirection::Down,"noise");
    require(findNearestEnabled(items,INavigation::Index{},MoveDirection::First),"choose","Home");
    step("choose",MoveDirection::Down,"ack");pgdown("ack","close");
    // Approximation acknowledgment enables Analyze; a completed draft enables Save.
    named("analyze")->yes=true;step("close",MoveDirection::Right,"analyze");
    named("save")->yes=true;step("save",MoveDirection::Left,"analyze");step("analyze",MoveDirection::Left,"close");
  }
  std::cout<<"PASS "<<checks<<" source-algorithm transitions across 10000 deterministic control-order shuffles; GUI_executed=false\n";
}
