#include "common.h"
double mean(const int64_t *a,int n) { double s=0; for(int i=0;i<n;i++)s+=(double)a[i]; return s/n; }
double variance(const int64_t *a,int n,double m) {double s=0; for(int i=0;i<n;i++){double d=(double)a[i]-m;s+=d*d;}return s/n;}
int main(int argc,char **argv) {
 if(argc<2 || argc>17)return bad(); int64_t a[16];
 for(int i=1;i<argc;i++)if(!number(argv[i],-10000,10000,&a[i-1]))return bad();
 double m=mean(a,argc-1); printf("mean=%.6f variance=%.6f\n",m,variance(a,argc-1,m)); return 0;
}
