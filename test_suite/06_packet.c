#include "common.h"
int nibble(unsigned char c) {if(c>='0'&&c<='9')return c-'0'; if(c>='a'&&c<='f')return c-'a'+10; if(c>='A'&&c<='F')return c-'A'+10; return -1;}
int decode(const char *s,uint8_t *out) {
 size_t n=strlen(s); if(n<8 || n>128 || n%2) return -1;
 for(size_t i=0;i<n/2;i++) {int a=nibble((unsigned char)s[2*i]),b=nibble((unsigned char)s[2*i+1]); if(a<0||b<0)return -1; out[i]=(uint8_t)(a*16+b);}
 return (int)(n/2);
}
int main(int argc,char **argv) {
 uint8_t data[64]; if(argc!=2) return bad(); int n=decode(argv[1],data);
 if(n<4 || data[0]!=0xa5 || data[1]!=(uint8_t)(n-4)) return bad();
 uint32_t sum=0; for(int i=4;i<n;i++) sum+=data[i];
 printf("id=%u length=%u checksum=%u\n",(unsigned)((uint32_t)data[2]<<8|data[3]),(unsigned)data[1],(unsigned)(sum&255)); return 0;
}
