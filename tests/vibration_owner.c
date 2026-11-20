#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <SDL3/SDL.h>
#include "../runtime/host.h"
#undef HOST_OVERRIDE
#define HOST_OVERRIDE(sym, fn)
#include "../runtime/ov_input.c"
static PlatMutex capture_lock = PLAT_MUTEX_INIT;
static PlatEvent entered, release_io;
static int block_io, failures, calls, accepted, zero_seen;
static volatile int32_t ready=1, generation=1, config_version=1, strength=100;
static VibrationValue output[2];
uint64_t kern_now_ns(void) { return SDL_GetTicksNS()+1; }
void rt_log(const char *fmt, ...) { (void)fmt; }
_Noreturn void rt_fatal(const char *fmt, ...) { fprintf(stderr,"unexpected fatal: %s\n",fmt);abort(); }
unsigned cfg_version(void) { return (unsigned)plat_cas32(&config_version,0,0); }
const char *cfg_get(const char *name) { (void)name;return "1"; }
double cfg_double(const char *name) { (void)name;return plat_cas32(&strength,0,0); }
int input_rumble_triggers_enabled(void) { return 0; }
uint32_t input_rumble_generation(void) { return (uint32_t)plat_cas32(&generation,0,0); }
int input_rumble_service(uint32_t *epoch) {
    *epoch=input_rumble_generation();int on=plat_cas32(&ready,0,0);
    if(!on) {plat_mutex_lock(&capture_lock);memset(output,0,sizeof output);plat_mutex_unlock(&capture_lock);}
    return on;
}
void input_rumble_shutdown_device(void) { plat_mutex_lock(&capture_lock);memset(output,0,sizeof output);++accepted;plat_mutex_unlock(&capture_lock); }
int ov_handheld(void) { return 0; }
int input_rumble_hd_epoch(float la,float lf,float lh,float lhf,float ra,float rf,float rh,float rhf,uint32_t ms,uint32_t epoch) {
    assert(la>=0&&la<=1&&lh>=0&&lh<=1&&ra>=0&&ra<=1&&rh>=0&&rh<=1);
    (void)ms;VibrationValue v[2]={{la,lf,lh,lhf},{ra,rf,rh,rhf}};
    plat_mutex_lock(&capture_lock);++calls;int blocked=block_io;plat_mutex_unlock(&capture_lock);
    if(blocked) {plat_event_set(&entered);plat_event_wait(&release_io);}
    plat_mutex_lock(&capture_lock);
    int ok=failures?0:1;if(failures)--failures;
    if(epoch!=input_rumble_generation())ok=-1;
    if(ok>0) {memcpy(output,v,sizeof output);++accepted;if(!la&&!lh&&!ra&&!rh)++zero_seen;}
    plat_mutex_unlock(&capture_lock);return ok;
}
static void batch(float a,float b) {
    uint32_t handles[]={3,0x10003};VibrationValue values[]={{a,160,a/2,320},{b,180,b/2,360}};
    Cpu c={0};c.x[0]=(uint64_t)(uintptr_t)handles;c.x[1]=(uint64_t)(uintptr_t)values;c.x[2]=2;
    ov_vib_send_many(&c);
}
static void wait_output(float a,float b) {
    uint64_t end=kern_now_ns()+1000000000ull;
    for(;;) {
        plat_mutex_lock(&capture_lock);int done=fabsf(output[0].amp_low-a)<.00001f&&fabsf(output[1].amp_low-b)<.00001f;plat_mutex_unlock(&capture_lock);
        if(done)return;assert(kern_now_ns()<end);SDL_Delay(1);
    }
}
int main(void) {
    _set_error_mode(_OUT_TO_STDERR);
    plat_event_init(&entered,1,0);plat_event_init(&release_io,1,0);
    batch(.2f,.3f);wait_output(.2f,.3f);
    assert(vib_last[0].amp_low==.2f&&vib_last[1].amp_low==.3f);
    plat_mutex_lock(&capture_lock);block_io=1;int previous_zeros=zero_seen;plat_mutex_unlock(&capture_lock);
    batch(.25f,.35f);plat_event_wait(&entered);
    uint64_t start=kern_now_ns();for(int i=0;i<10000;++i)batch(.4f,.5f);
    assert(kern_now_ns()-start<500000000ull);
    batch(0,0);batch(.45f,.55f);
    plat_mutex_lock(&capture_lock);block_io=0;plat_mutex_unlock(&capture_lock);plat_event_set(&release_io);
    wait_output(.45f,.55f);plat_mutex_lock(&capture_lock);assert(zero_seen>previous_zeros);plat_mutex_unlock(&capture_lock);
    puts("PASS: stereo batch, 10000 nonblocking publications during backend stall, latched Stop before new activation");
    plat_mutex_lock(&capture_lock);failures=2;plat_mutex_unlock(&capture_lock);
    batch(.3f,.4f);wait_output(.3f,.4f);
    const float previous_overflow = 103.0f / 255.0f;
    batch(previous_overflow,1);wait_output(previous_overflow,1);
    plat_mutex_lock(&capture_lock);
    assert(output[0].amp_low==previous_overflow&&output[1].amp_low==1);
    plat_mutex_unlock(&capture_lock);
    plat_xchg32(&strength,50);plat_inc32(&config_version);batch(.2f,.4f);wait_output(.1f,.2f);
    assert(vib_last[0].amp_low==.2f&&vib_last[1].amp_low==.4f);
    plat_xchg32(&strength,0);plat_inc32(&config_version);batch(.3f,.4f);wait_output(0,0);
    plat_xchg32(&strength,100);plat_inc32(&config_version);batch(.2f,.3f);wait_output(.2f,.3f);
    Cpu permission={0};permission.x[0]=0;ov_vib_permit(&permission);wait_output(0,0);
    permission.x[0]=1;ov_vib_permit(&permission);SDL_Delay(15);
    plat_mutex_lock(&capture_lock);assert(output[0].amp_low==0&&output[1].amp_low==0);plat_mutex_unlock(&capture_lock);
    puts("PASS: retry, one-time strength, raw readback, permission stop and no stale re-enable");
    batch(.2f,.3f);wait_output(.2f,.3f);
    SDL_Delay(150);VibrationValue right={.35f,180,.1f,360};play(1,&right);
    wait_output(0,.35f);wait_output(0,0);
    puts("PASS: independent per-side 250ms expiry without game updates");
    batch(.2f,.3f);wait_output(.2f,.3f);
    plat_xchg32(&ready,0);plat_inc32(&generation);SDL_Delay(20);
    plat_xchg32(&ready,1);plat_inc32(&generation);SDL_Delay(15);
    plat_mutex_lock(&capture_lock);assert(output[0].amp_low==0&&output[1].amp_low==0);plat_mutex_unlock(&capture_lock);
    batch(.4f,.5f);wait_output(.4f,.5f);
    input_vibration_shutdown();wait_output(0,0);
    plat_mutex_lock(&capture_lock);int n=calls;plat_mutex_unlock(&capture_lock);
    batch(.9f,.9f);SDL_Delay(10);plat_mutex_lock(&capture_lock);assert(calls==n);plat_mutex_unlock(&capture_lock);
    puts("PASS: connection epochs, shutdown joins and rejects later output");return 0;
}
