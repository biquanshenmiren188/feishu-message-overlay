using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
namespace Overlay.App;
// Explicit test mode only. Injects input ONLY while this synthetic window is foreground.
internal static class BrowserInputFixture
{
    [StructLayout(LayoutKind.Sequential)]private struct MouseInput {public int x,y;public uint data,flags,time;public nuint extra;}
    [StructLayout(LayoutKind.Sequential)]private struct KeyInput {public ushort key,scan;public uint flags,time;public nuint extra;}
    [StructLayout(LayoutKind.Explicit)]private struct Union {[FieldOffset(0)]public MouseInput mouse;[FieldOffset(0)]public KeyInput key;}
    [StructLayout(LayoutKind.Sequential)]private struct Input {public uint type;public Union data;}
    [DllImport("user32.dll")]private static extern uint SendInput(uint count,Input[] inputs,int size);
    [DllImport("user32.dll")]private static extern bool SetCursorPos(int x,int y);
    [DllImport("user32.dll")]private static extern uint GetWindowThreadProcessId(nint hwnd,out uint pid);
    internal static void ClickSyntheticWindow(Window window,int expectedForegroundPid)
    {
        if(!App.SmokeMode)throw new InvalidOperationException("Synthetic mode only");
        GetWindowThreadProcessId(DragYield.GetForegroundWindow(),out var pid);
        if(pid!=expectedForegroundPid && pid!=Environment.ProcessId)throw new InvalidOperationException("Unexpected foreground; no input sent");
        var point=window.PointToScreen(new Point(145,14));SetCursorPos((int)point.X,(int)point.Y);
        Input[] input=[new(){data=new(){mouse=new(){flags=2}}},new(){data=new(){mouse=new(){flags=4}}}];
        if(SendInput(2,input,Marshal.SizeOf<Input>())!=2)throw new InvalidOperationException("Synthetic click rejected");
    }
    internal static async Task RunAsync(string token)
    {
        using var ready=EventWaitHandle.OpenExisting(token+"-ready");using var next=EventWaitHandle.OpenExisting(token+"-next");using var done=EventWaitHandle.OpenExisting(token+"-done");
        var text=new System.Windows.Controls.TextBox{Text="Synthetic input only; no network",Margin=new Thickness(12)};
        System.Windows.Input.InputMethod.SetIsInputMethodEnabled(text,false);
        var window=new Window{Title="Synthetic browser-input verification",Width=340,Height=200,Left=80,Top=100,ShowInTaskbar=false,Content=text};
        window.Show();window.Activate();text.Focus();var hwnd=new WindowInteropHelper(window).Handle;
        await Task.Delay(600);ready.Set();
        for(var step=0;step<8;step++)
        {
            if(!await Task.Run(()=>next.WaitOne(15000)))throw new InvalidOperationException("Test command timed out");
            if(DragYield.GetForegroundWindow()!=hwnd)throw new InvalidOperationException("Synthetic window lost foreground; no input sent");
            var point=text.PointToScreen(new Point(25,25));SetCursorPos((int)point.X,(int)point.Y);
            // Recheck immediately before dispatch, never type into another foreground window.
            if(DragYield.GetForegroundWindow()!=hwnd)throw new InvalidOperationException("Foreground changed; no input sent");
            Input[] input=step is 0 or 6?[new(){data=new(){mouse=new(){x=10,flags=1}}}]:step is 1 or 4?[new(){data=new(){mouse=new(){data=120,flags=0x800}}}]:step is 2 or 5?
                [new(){type=1,data=new(){key=new(){key=0x41}}},new(){type=1,data=new(){key=new(){key=0x41,flags=2}}}]:
                [new(){data=new(){mouse=new(){flags=2}}},new(){data=new(){mouse=new(){flags=4}}}];
            if(SendInput((uint)input.Length,input,Marshal.SizeOf<Input>())!=input.Length)throw new InvalidOperationException("Synthetic input rejected");
            await Task.Delay(50);done.Set();
        }
        await Task.Run(()=>next.WaitOne(15000));window.Close();
    }
}
