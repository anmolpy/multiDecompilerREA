#include "common.h"
typedef struct Node { int32_t value; uint16_t weight; struct Node *next; } Node;
int64_t weighted_sum(const Node *n) {
 int64_t total=0; for(;n;n=n->next) total+=(int64_t)n->value*n->weight; return total;
}
int main(int argc,char **argv) {
 if(argc<2 || argc>17) return bad(); Node nodes[16];
 for(int i=1;i<argc;i++) {int64_t v; if(!number(argv[i],-10000,10000,&v)) return bad();
 nodes[i-1].value=(int32_t)v; nodes[i-1].weight=(uint16_t)i;
 nodes[i-1].next=i+1<argc?&nodes[i]:NULL;}
 printf("%" PRId64 "\n",weighted_sum(nodes)); return 0;
}
