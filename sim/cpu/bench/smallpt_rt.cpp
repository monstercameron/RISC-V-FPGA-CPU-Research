// RT-P: smallpt for the bare-metal RV64 cores and the native reference.
//
// Derived from smallpt, a path tracer by Kevin Beason (smallpt.cpp from
// https://www.kevinbeason.com/smallpt/smallpt.tar.gz, SHA-256
// 43fcaca577824073f2ab384c0aa0fda5acdd57b6dee5041bdaa1d99a37f69fa1).
// Copyright (c) 2006-2008 Kevin Beason; MIT licence, see
// licenses/SMALLPT-LICENSE.txt. The scene, camera, sampling, materials and
// recursion are smallpt's. Changes, for a deterministic single-thread run that
// gives the same bits on every target:
//   - erand48 is the same 48-bit LCG and conversion as glibc's, in code;
//   - sqrt, sin, cos, fabs come from rt_math.c (sqrt correctly rounded as
//     everywhere; sin and cos are rt_math's own, not glibc's);
//   - w, h and samples are parameters; no OpenMP, no output file, no progress
//     line; the image is a static buffer, cleared before the render;
//   - constexpr constructors, so the scene is static data (bare metal runs no
//     global constructors); the narrowing in Xi[3]={0,0,y*y*y} is an explicit
//     (unsigned short) cast, as g++ treats the original;
//   - radiance() counts its calls (rays cast) in rt_segments.
// Built with -ffp-contract=off. SPDX-License-Identifier: MIT
#include "rt_bench.h"
#include "rt_math.h"

static inline double pt_erand48(unsigned short xi[3]) {
  rt_u64 x = (rt_u64)xi[0] | ((rt_u64)xi[1] << 16) | ((rt_u64)xi[2] << 32);
  x = (x * 0x5DEECE66Dull + 0xBull) & 0xFFFFFFFFFFFFull;
  xi[0] = (unsigned short)x; xi[1] = (unsigned short)(x >> 16); xi[2] = (unsigned short)(x >> 32);
  return (double)x * (1.0 / 281474976710656.0);
}
#define erand48 pt_erand48
#define sqrt rt_sqrt
#define sin rt_sin
#define cos rt_cos
#define fabs rt_fabs
#define M_PI RT_PI

struct Vec {
  double x, y, z;
  constexpr Vec(double x_=0, double y_=0, double z_=0) : x(x_), y(y_), z(z_) {}
  Vec operator+(const Vec &b) const { return Vec(x+b.x,y+b.y,z+b.z); }
  Vec operator-(const Vec &b) const { return Vec(x-b.x,y-b.y,z-b.z); }
  constexpr Vec operator*(double b) const { return Vec(x*b,y*b,z*b); }
  Vec mult(const Vec &b) const { return Vec(x*b.x,y*b.y,z*b.z); }
  Vec& norm(){ return *this = *this * (1/sqrt(x*x+y*y+z*z)); }
  double dot(const Vec &b) const { return x*b.x+y*b.y+z*b.z; }
  Vec operator%(Vec&b){return Vec(y*b.z-z*b.y,z*b.x-x*b.z,x*b.y-y*b.x);}
};
struct Ray { Vec o, d; Ray(Vec o_, Vec d_) : o(o_), d(d_) {} };
enum Refl_t { DIFF, SPEC, REFR };
struct Sphere {
  double rad; Vec p, e, c; Refl_t refl;
  constexpr Sphere(double rad_, Vec p_, Vec e_, Vec c_, Refl_t refl_): rad(rad_), p(p_), e(e_), c(c_), refl(refl_) {}
  double intersect(const Ray &r) const {
    Vec op = p-r.o;
    double t, eps=1e-4, b=op.dot(r.d), det=b*b-op.dot(op)+rad*rad;
    if (det<0) return 0; else det=sqrt(det);
    return (t=b-det)>eps ? t : ((t=b+det)>eps ? t : 0);
  }
};
static constexpr Sphere spheres[] = {
  Sphere(1e5, Vec( 1e5+1,40.8,81.6), Vec(),Vec(.75,.25,.25),DIFF),//Left
  Sphere(1e5, Vec(-1e5+99,40.8,81.6),Vec(),Vec(.25,.25,.75),DIFF),//Rght
  Sphere(1e5, Vec(50,40.8, 1e5),     Vec(),Vec(.75,.75,.75),DIFF),//Back
  Sphere(1e5, Vec(50,40.8,-1e5+170), Vec(),Vec(),           DIFF),//Frnt
  Sphere(1e5, Vec(50, 1e5, 81.6),    Vec(),Vec(.75,.75,.75),DIFF),//Botm
  Sphere(1e5, Vec(50,-1e5+81.6,81.6),Vec(),Vec(.75,.75,.75),DIFF),//Top
  Sphere(16.5,Vec(27,16.5,47),       Vec(),Vec(1,1,1)*.999, SPEC),//Mirr
  Sphere(16.5,Vec(73,16.5,78),       Vec(),Vec(1,1,1)*.999, REFR),//Glas
  Sphere(600, Vec(50,681.6-.27,81.6),Vec(12,12,12),  Vec(), DIFF) //Lite
};
inline double clamp(double x){ return x<0 ? 0 : x>1 ? 1 : x; }
inline bool intersect(const Ray &r, double &t, int &id){
  double n=sizeof(spheres)/sizeof(Sphere), d, inf=t=1e20;
  for(int i=int(n);i--;) if((d=spheres[i].intersect(r))&&d<t){t=d;id=i;}
  return t<inf;
}
static rt_u64 rt_segments;
Vec radiance(const Ray &r, int depth, unsigned short *Xi){
  rt_segments++;
  double t; int id=0;
  if (!intersect(r, t, id)) return Vec();
  const Sphere &obj = spheres[id];
  Vec x=r.o+r.d*t, n=(x-obj.p).norm(), nl=n.dot(r.d)<0?n:n*-1, f=obj.c;
  double p = f.x>f.y && f.x>f.z ? f.x : f.y>f.z ? f.y : f.z;
  if (++depth>5) if (erand48(Xi)<p) f=f*(1/p); else return obj.e;
  if (obj.refl == DIFF){
    double r1=2*M_PI*erand48(Xi), r2=erand48(Xi), r2s=sqrt(r2);
    Vec w=nl, u=((fabs(w.x)>.1?Vec(0,1):Vec(1))%w).norm(), v=w%u;
    Vec d = (u*cos(r1)*r2s + v*sin(r1)*r2s + w*sqrt(1-r2)).norm();
    return obj.e + f.mult(radiance(Ray(x,d),depth,Xi));
  } else if (obj.refl == SPEC)
    return obj.e + f.mult(radiance(Ray(x,r.d-n*2*n.dot(r.d)),depth,Xi));
  Ray reflRay(x, r.d-n*2*n.dot(r.d));
  bool into = n.dot(nl)>0;
  double nc=1, nt=1.5, nnt=into?nc/nt:nt/nc, ddn=r.d.dot(nl), cos2t;
  if ((cos2t=1-nnt*nnt*(1-ddn*ddn))<0)
    return obj.e + f.mult(radiance(reflRay,depth,Xi));
  Vec tdir = (r.d*nnt - n*((into?1:-1)*(ddn*nnt+sqrt(cos2t)))).norm();
  double a=nt-nc, b=nt+nc, R0=a*a/(b*b), c = 1-(into?-ddn:tdir.dot(n));
  double Re=R0+(1-R0)*c*c*c*c*c,Tr=1-Re,P=.25+.5*Re,RP=Re/P,TP=Tr/(1-P);
  return obj.e + f.mult(depth>2 ? (erand48(Xi)<P ?
    radiance(reflRay,depth,Xi)*RP:radiance(Ray(x,tdir),depth,Xi)*TP) :
    radiance(reflRay,depth,Xi)*Re+radiance(Ray(x,tdir),depth,Xi)*Tr);
}

static Vec image[RT_PT_W * RT_PT_H];

extern "C" void rt_smallpt(int w, int h, int samps, rt_results *res){   // smallpt's main loop
  Ray cam(Vec(50,52,295.6), Vec(0,-0.042612,-1).norm());
  Vec cx=Vec(w*.5135/h), cy=(cx%cam.d).norm()*.5135, r, *c=image;
  for (int i=0; i<w*h; i++) c[i]=Vec();
  rt_segments = 0;
  for (int y=0; y<h; y++){
    for (unsigned short x=0, Xi[3]={0,0,(unsigned short)(y*y*y)}; x<w; x++)
      for (int sy=0, i=(h-y-1)*w+x; sy<2; sy++)
        for (int sx=0; sx<2; sx++, r=Vec()){
          for (int s=0; s<samps; s++){
            double r1=2*erand48(Xi), dx=r1<1 ? sqrt(r1)-1: 1-sqrt(2-r1);
            double r2=2*erand48(Xi), dy=r2<1 ? sqrt(r2)-1: 1-sqrt(2-r2);
            Vec d = cx*( ( (sx+.5 + dx)/2 + x)/w - .5) +
                    cy*( ( (sy+.5 + dy)/2 + y)/h - .5) + cam.d;
            r = r + radiance(Ray(cam.o+d*140,d.norm()),0,Xi)*(1./samps);
          }
          c[i] = c[i] + Vec(clamp(r.x),clamp(r.y),clamp(r.z))*.25;
        }
  }
  res->paths = (rt_u64)w * h * 4 * samps;
  res->segments = rt_segments;
}

// FNV-1a over the bytes of the linear (pre-gamma) image, x, y, z per pixel.
extern "C" rt_u64 rt_smallpt_hash(int w, int h){
  rt_u64 hash = 1469598103934665603ull;
  const unsigned char* b = (const unsigned char*)image;
  for (rt_u64 i = 0; i < (rt_u64)w * h * sizeof(Vec); i++) { hash ^= b[i]; hash *= 1099511628211ull; }
  return hash;
}
