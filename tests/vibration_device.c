// Opt-in real-device check of the actual HLE owner and SDL input backend.
#include <stdio.h>
#include <stdarg.h>
#include <SDL3/SDL.h>
#include "../runtime/host.h"
#undef HOST_OVERRIDE
#define HOST_OVERRIDE(sym, fn)
#define lock input_device_lock
#include "../runtime/input.c"
#undef lock
#include "../runtime/ov_input.c"
static volatile int32_t foreground=1;
int ikb_foreground(void) { return plat_cas32(&foreground,0,0); }
uint64_t kern_now_ns(void) { return SDL_GetTicksNS()+1; }
void rt_log(const char *fmt, ...) { (void)fmt; }
_Noreturn void rt_fatal(const char *fmt, ...) { fprintf(stderr,"fatal: %s\n",fmt);abort(); }
int ov_handheld(void) { return 0; }
static void emit(float a,float b) {
    uint32_t h[]={3,0x10003};VibrationValue v[]={{a,160,.02f,320},{b,180,.02f,360}};
    Cpu c={0};c.x[0]=(uint64_t)(uintptr_t)h;c.x[1]=(uint64_t)(uintptr_t)v;c.x[2]=2;ov_vib_send_many(&c);
}
int main(int argc,char **argv) {
    if(argc!=2||strcmp(argv[1],"--play")) {puts("Usage: vibration_device --play (synthetic low-amplitude test)");return 2;}
    cfg_init();cfg_set("TOTK_RUMBLE_STRENGTH","100");cfg_set("TOTK_PAD_LAYOUT","auto");
    SDL_SetHint(SDL_HINT_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT,"0x057e/0x2069");
    SDL_SetHint("SDL_JOYSTICK_HIDAPI_RUMBLE_TRACE","1");SDL_SetLogPriority(SDL_LOG_CATEGORY_INPUT,SDL_LOG_PRIORITY_INFO);
    uint32_t gen;
    if(!input_rumble_service(&gen)||!pad||SDL_GetGamepadVendor(pad)!=0x057e||SDL_GetGamepadProduct(pad)!=0x2069) {
        puts("SKIP no supported controller");input_rumble_shutdown_device();return 77;
    }
    uint64_t begin=kern_now_ns(),max_publish=0;
    for(unsigned i=0;i<200;++i) {
        uint64_t at=kern_now_ns();emit(.02f+.03f*(i%25)/24.f,.025f);
        uint64_t cost=kern_now_ns()-at;if(cost>max_publish)max_publish=cost;
        uint64_t due=begin+(uint64_t)(i+1)*5000000,now=kern_now_ns();if(now<due)SDL_DelayPrecise(due-now);
    }
    plat_xchg32(&foreground,0);SDL_Delay(30);
    plat_xchg32(&foreground,1);emit(.025f,.025f);SDL_Delay(20);
    input_vibration_shutdown();
    printf("TOTK HLE owner: 200 native-timed stereo batches; max publication %.3f ms; focus/shutdown completed\n",max_publish/1e6);
    return 0;
}

// The standalone fixture has no window, renderer or guest simulation.
__typeof__(gfx_counters) gfx_counters;
int ikb_down(int key) {(void)key;return 0;}
int ikb_escape(void) {return 0;}
int ikb_captured(void) {return 0;}
void ikb_mouse_take(int32_t *x,int32_t *y) {*x=*y=0;}
uint32_t ikb_mouse_travel(void) {return 0;}
int32_t ikb_wheel_take(void) {return 0;}
void ikb_cursor_update(void) {}
void ikb_menu_closed(void) {}
uint64_t frame_step_ticks(void) {return 0;}
int64_t frame_step_world_us(void) {return -1;}
float cam_speed_applied(void) {return 1;}
int menu_cursor_pointer(void) {return 0;}
int menu_cursor_shortcut(void) {return -1;}
int menu_cursor_map(void) {return 0;}
int menu_cursor_dialogue(void) {return 0;}
int menu_cursor_strip(void) {return 0;}
int menu_cursor_camera(void) {return 0;}
int menu_cursor_menu(void) {return 0;}
void menu_cursor_poll(uint64_t *b) {(void)b;}
int menu_is_open(void) {return 0;}
void menu_toggle(void) {}
void menu_perf_cycle(void) {}
int input_direct_mouse_active(void) {return 0;}
int input_direct_mouse_enabled(void) {return 0;}
int input_direct_mouse_shake(void) {return 0;}
void input_direct_mouse_radial(int32_t x,int32_t y,float s,float c[2],int32_t o[2]) {(void)x;(void)y;(void)s;(void)c;o[0]=o[1]=0;}
void input_direct_mouse_row(int32_t x,float s,uint64_t n,InputMouseRow *r,int32_t o[2]) {(void)x;(void)s;(void)n;(void)r;o[0]=o[1]=0;}
MotionFusion *motion_global(void) {return NULL;}
void motion_feed(MotionFusion *m,const double a[3],const double g[3],uint64_t t) {(void)m;(void)a;(void)g;(void)t;}
int motion_calibration_enabled(void) {return 0;}
void motion_calibrate_start(MotionFusion *m,const char *pad,uint64_t t) {(void)m;(void)pad;(void)t;}
int motion_calib_poll(MotionFusion *m,uint64_t t) {(void)m;(void)t;return 0;}
void motion_bias_reset(MotionFusion *m) {(void)m;}
void motion_bias_load(MotionFusion *m) {(void)m;}
void motion_restart(MotionFusion *m) {(void)m;}
int freecam_available(void) {return 0;}
int freecam_state(void) {return FREECAM_OFF;}
void freecam_cycle(void) {}
void freecam_pad(const FreecamPad *p) {(void)p;}
void freecam_speed_click(int faster) {(void)faster;}
int quicksave_on(void) {return 0;}
void quicksave_keys(uint8_t *down,int act) {(void)down;(void)act;}
void quicksave_request(int load) {(void)load;}
int quicksave_poll(uint64_t *b,int32_t *lx,int32_t *ly,int32_t *rx,int32_t *ry) {
    (void)b;(void)lx;(void)ly;(void)rx;(void)ry;return 0;
}
int quicksave_busy(void) {return 0;}
int gameplay_tweaks_capture_needed(void) {return 0;}
void gameplay_tweaks_reset(void) {}
int gameplay_tweaks_strip_wheel(uint64_t buttons) {(void)buttons;return 0;}
void gameplay_tweaks_apply(uint64_t frame,int active,uint64_t *b,int32_t *lx,int32_t *ly,int32_t *rx,int32_t *ry) {
    (void)frame;(void)active;(void)b;(void)lx;(void)ly;(void)rx;(void)ry;
}
int romfs_shaped_prompts_ready(const char *folder,unsigned w,unsigned h) {(void)folder;(void)w;(void)h;return 0;}
