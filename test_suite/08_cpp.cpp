#include "common.h"
#include <memory>
#include <stdexcept>
class Rule {public: virtual ~Rule()=default; virtual int64_t score(int64_t x) const=0;};
class Linear:public Rule {public:int64_t score(int64_t x)const override{return x*3+7;}};
class Square:public Rule {public:int64_t score(int64_t x)const override{return x*x-2;}};
std::unique_ptr<Rule> make_rule(int mode){if(mode==0)return std::make_unique<Linear>();return std::make_unique<Square>();}
int64_t evaluate(const Rule& r,int64_t x){if(x<0)throw std::runtime_error("negative");return r.score(x);}
int main(int argc,char **argv){int64_t m,x;
 if(argc!=3||!number(argv[1],0,1,&m)||!number(argv[2],-10000,10000,&x))return bad();
 try {auto r=make_rule((int)m); int64_t result=evaluate(*r,x); printf("score=%" PRId64 "\n",result); return 0;} catch(const std::runtime_error& e) {printf("error=%s\n",e.what());return 3;}
}
