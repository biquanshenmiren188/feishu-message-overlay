using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
namespace Overlay.App;
// Isolated synthetic window. No user windows, titles or input contents are inspected.
internal static class DragYieldFixture
{
    [DllImport("user32.dll")]private static extern bool PostMessage(nint h,uint message,nint w,nint l);
    internal static async Task RunAsync(string action)
    {
        var window=new Window{Title="Synthetic move/resize verification",Width=280,Height=160,Left=80,Top=100,ShowInTaskbar=false,ShowActivated=false,Content="Synthetic test only"};
        window.Show();var handle=new WindowInteropHelper(window).Handle;
        await Task.Delay(350);
        PostMessage(handle,0x112,action=="size"?0xF008:0xF010,0);
        await Task.Delay(250);PostMessage(handle,0x100,0x27,0);PostMessage(handle,0x101,0x27,0);
        await Task.Delay(500);PostMessage(handle,0x100,action=="cancel"?0x1B:0x0D,0);PostMessage(handle,0x101,action=="cancel"?0x1B:0x0D,0);
        await Task.Delay(800);window.Close();
    }
}
