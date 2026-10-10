using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Threading;
namespace Overlay.App;

// Observes HWND metadata and mouse-down targets only; never records input or reads window content.
internal sealed class DragYield : IDisposable
{
    private delegate void WinEvent(nint hook,uint ev,nint hwnd,int obj,int child,uint thread,uint time);
    private delegate nint MouseEvent(int code,nint message,nint data);
    [StructLayout(LayoutKind.Sequential)] private struct NativePoint {public int x,y;}
    [DllImport("user32.dll")] private static extern nint SetWindowsHookExW(int id,MouseEvent callback,nint module,uint thread);
    [DllImport("user32.dll")] private static extern bool UnhookWindowsHookEx(nint hook);
    [DllImport("user32.dll")] private static extern nint CallNextHookEx(nint hook,int code,nint message,nint data);
    [DllImport("user32.dll")] private static extern nint WindowFromPoint(NativePoint point);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode)] private static extern nint GetModuleHandleW(string? name);
    [DllImport("user32.dll")] private static extern nint SetWinEventHook(uint first,uint last,nint module,WinEvent callback,uint process,uint thread,uint flags);
    [DllImport("user32.dll")] private static extern bool UnhookWinEvent(nint hook);
    [DllImport("user32.dll")] private static extern nint GetAncestor(nint hwnd,uint flags);
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(nint hwnd,out uint process);
    [DllImport("user32.dll")] private static extern bool IsWindow(nint hwnd);
    [DllImport("user32.dll")] private static extern bool IsWindowVisible(nint hwnd);
    [DllImport("user32.dll")] private static extern bool IsIconic(nint hwnd);
    [DllImport("user32.dll")] internal static extern nint GetForegroundWindow();
    [DllImport("user32.dll")] private static extern bool SetWindowPos(nint hwnd,nint after,int x,int y,int width,int height,uint flags);
    [DllImport("user32.dll",EntryPoint="GetWindowLongPtrW")] private static extern nint GetStyle(nint hwnd,int index);
    [DllImport("user32.dll")] private static extern bool GetGUIThreadInfo(uint thread,ref GuiInfo info);
    [DllImport("user32.dll")] private static extern bool GetLastInputInfo(ref LastInput info);
    [StructLayout(LayoutKind.Sequential)] private struct LastInput {public uint size,time;}
    [StructLayout(LayoutKind.Sequential)] private struct GuiInfo {public uint size,flags;public nint active,focus,capture,menu,move,caret;public int left,top,right,bottom;}
    private readonly Window window;
    private readonly Func<bool> intended;
    private readonly WinEvent callback;
    private readonly MouseEvent mouseCallback;
    private nint mouseHook;
    internal bool ClickWatchActive=>mouseHook!=0;
    internal int ObservedClicks {get;private set;}
    internal int ExternalClicks {get;private set;}
    private readonly DispatcherTimer restore=new(){Interval=TimeSpan.FromSeconds(5)};
    private readonly DispatcherTimer recovery=new(){Interval=TimeSpan.FromSeconds(2)};
    private readonly DispatcherTimer browserWatch=new(){Interval=TimeSpan.FromMilliseconds(500)};
    private nint hook,foregroundHook,other,browser;
    private uint lastInput;
    private bool moving,browserYield,ownMenu;
    private uint otherThread;
    private bool disposed;
    internal bool Yielding=>moving || browserYield;
    internal bool BrowserWatchActive=>browserWatch.IsEnabled;
    internal int ActiveTimerCount=>(browserWatch.IsEnabled?1:0)+(restore.IsEnabled?1:0)+(recovery.IsEnabled?1:0);
    internal static int SyntheticBrowserProcessId {get;set;}
    internal bool IsHooked=>hook!=0 && foregroundHook!=0;
    internal bool RestoreKeptForeground {get;private set;}
    internal bool NativeTopmost=>(GetStyle(new WindowInteropHelper(window).Handle,-20)&8)!=0;
    internal event Action<string>? Changed;
    internal DragYield(Window window,Func<bool> intended)
    {
        this.window=window;this.intended=intended;callback=OnEvent;mouseCallback=OnMouse;
        hook=SetWinEventHook(0xA,0xB,0,callback,0,0,2); // OUTOFCONTEXT | SKIPOWNPROCESS
        foregroundHook=SetWinEventHook(3,3,0,callback,0,0,0); // Foreground metadata only, including own windows.
        lastInput=InputTime();browserWatch.Tick+=(_,_)=>CheckBrowserInput();
        restore.Tick+=(_,_)=>{restore.Stop();recovery.Stop();moving=false;if(!browserYield)other=0;RestoreWithoutActivation();};
        recovery.Tick+=(_,_)=>{
            var info=new GuiInfo{size=(uint)Marshal.SizeOf<GuiInfo>()};
            if(!IsWindow(other) || !IsWindowVisible(other) || IsIconic(other) || !GetGUIThreadInfo(otherThread,ref info) || (info.flags&16)==0)End();
        };
        window.IsVisibleChanged+=VisibilityChanged;window.StateChanged+=StateChanged;window.Closed+=WindowClosed;
    }
    private void VisibilityChanged(object? sender,DependencyPropertyChangedEventArgs e)=>RefreshVisibility();
    private void StateChanged(object? sender,EventArgs e)=>RefreshVisibility();
    private void WindowClosed(object? sender,EventArgs e)=>Dispose();
    private void UpdateClickWatch()
    {
        if(Available && mouseHook==0)mouseHook=SetWindowsHookExW(14,mouseCallback,GetModuleHandleW(null),0);
        else if(!Available && mouseHook!=0){UnhookWindowsHookEx(mouseHook);mouseHook=0;}
    }
    private nint OnMouse(int code,nint message,nint data)
    {
        // Only button-down initiates yield. Move, wheel and keyboard only extend an existing idle period.
        // Forward every event unchanged; do minimal work in the native hook.
        if(code>=0 && Available && (message==0x201 || message==0x204 || message==0x207 || message==0x20B))
        {
            ObservedClicks++;
            var target=GetAncestor(WindowFromPoint(Marshal.PtrToStructure<NativePoint>(data)),2);
            if(IsExternalWindow(target)){ExternalClicks++;window.Dispatcher.BeginInvoke(()=>ClickedExternal(target),DispatcherPriority.Background);}
        }
        return CallNextHookEx(mouseHook,code,message,data);
    }
    private void ClickedExternal(nint target)
    {
        if(!Available || !IsExternalWindow(target))return;
        browser=target;other=target;lastInput=InputTime();browserYield=true;
        Apply();browserWatch.Start();Changed?.Invoke("browser_yielded");
    }
    private void RefreshVisibility(){if(!window.IsVisible || window.WindowState==WindowState.Minimized){Cancel();}else {Apply();RefreshBrowser();}}
    private void OnEvent(nint h,uint ev,nint hwnd,int obj,int child,uint thread,uint time)
    {
        if(disposed || hwnd==0 || obj!=0 || child!=0)return;
        window.Dispatcher.BeginInvoke(()=>Handle(ev,hwnd),DispatcherPriority.Normal);
    }
    private void Handle(uint ev,nint hwnd)
    {
        if(disposed)return;
        if(ev==3){RefreshBrowser();return;}
        if(ev==0xB){if(hwnd==other)End();return;}
        if(!intended() || !window.IsVisible || window.WindowState==WindowState.Minimized || GetAncestor(hwnd,2)!=hwnd)return;
        var thread=GetWindowThreadProcessId(hwnd,out var process);if(process==(uint)Environment.ProcessId)return;
        restore.Stop();other=hwnd;otherThread=thread;moving=true;
        if(IsExternalWindow(hwnd)){browser=hwnd;browserYield=true;lastInput=InputTime();browserWatch.Start();}
        Apply();recovery.Start();Changed?.Invoke("yielded");
    }
    private void End(){recovery.Stop();restore.Stop();if(moving)restore.Start();}
    internal void IntentChanged(){if(!intended())Cancel();else {Apply();RefreshBrowser();}}
    private void Cancel(){restore.Stop();recovery.Stop();browserWatch.Stop();other=0;browser=0;moving=false;browserYield=false;lastInput=InputTime();Apply();}
    private static uint InputTime(){var info=new LastInput{size=8};return GetLastInputInfo(ref info)?info.time:unchecked((uint)Environment.TickCount64);}
    private bool Available=>!disposed && intended() && window.IsVisible && window.WindowState!=WindowState.Minimized && !ownMenu;
    private static bool IsExternalWindow(nint hwnd)
    {
        GetWindowThreadProcessId(hwnd,out var pid);if(pid==0 || pid==(uint)Environment.ProcessId)return false;
        if(App.SmokeMode)return pid==SyntheticBrowserProcessId;
        return IsWindow(hwnd) && IsWindowVisible(hwnd) && !IsIconic(hwnd);
    }
    private void RefreshBrowser()
    {
        UpdateClickWatch();
        var foreground=GetForegroundWindow();
        if(!Available || !IsExternalWindow(foreground))
        {
            browserWatch.Stop();browser=0;lastInput=InputTime();
            if(browserYield){browserYield=false;RestoreWithoutActivation();}return;
        }
        browser=foreground;CheckBrowserInput();browserWatch.Start();
    }
    private void CheckBrowserInput()
    {
        if(!Available || GetForegroundWindow()!=browser){RefreshBrowser();return;}
        var input=InputTime();
        if(input!=lastInput)
        {
            lastInput=input;
        }
        var age=unchecked((uint)Environment.TickCount64-input);
        if(browserYield && age>=5000 && age<0x80000000){browserYield=false;if(!moving)other=0;RestoreWithoutActivation();}
    }
    internal void OwnInput(bool menu=false){ownMenu=menu;lastInput=InputTime();if(browserYield){browserYield=false;RestoreWithoutActivation();}if(menu)browserWatch.Stop();UpdateClickWatch();}
    internal void MenuClosed(){ownMenu=false;lastInput=InputTime();RefreshBrowser();}
    private void RestoreWithoutActivation(){var foreground=GetForegroundWindow();Apply();RestoreKeptForeground=foreground==GetForegroundWindow();if(!Yielding)Changed?.Invoke("restored");}
    private void Apply()
    {
        if(disposed)return;
        UpdateClickWatch();
        var hwnd=new WindowInteropHelper(window).Handle;if(hwnd==0)return;
        SetWindowPos(hwnd,intended() && !Yielding?(nint)(-1):(nint)(-2),0,0,0,0,0x213); // no size/move/activate/owner reorder
        if(Yielding && IsWindow(other) && (GetStyle(other,-20)&8)==0)SetWindowPos(hwnd,other,0,0,0,0,0x213);
    }
    public void Dispose(){if(disposed)return;Cancel();disposed=true;UpdateClickWatch();if(hook!=0)UnhookWinEvent(hook);if(foregroundHook!=0)UnhookWinEvent(foregroundHook);hook=0;foregroundHook=0;window.IsVisibleChanged-=VisibilityChanged;window.StateChanged-=StateChanged;window.Closed-=WindowClosed;}
}
