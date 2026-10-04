using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;
using System.Windows.Media.Imaging;
namespace Overlay.App;
internal static class WindowAlpha
{
    [DllImport("user32.dll", EntryPoint="GetWindowLongPtrW")] private static extern nint GetStyle(nint hwnd,int index);
    // Per-pixel layered HWND is required. An opaque HWND fades content against
    // its own background instead of revealing the desktop behind the window.
    internal static bool Set(Window window,double value)
    {window.Opacity=1;if(window is MainWindow panel)panel.PaintPanelBackground(value);else window.Background=new SolidColorBrush(Color.FromArgb((byte)Math.Round(Math.Clamp(value,.6,1)*255),255,255,255));return window.AllowsTransparency;}
    internal static bool HasNativeLayered(Window window)
    {var handle=new WindowInteropHelper(window).Handle;return handle!=0 && (GetStyle(handle,-20)&0x80000)!=0;}
    internal static byte? Read(Window window)
    {
        var handle=new WindowInteropHelper(window).Handle;
        if(handle==0 || !window.AllowsTransparency || (GetStyle(handle,-20)&0x80000)==0)return null;
        var bitmap=new RenderTargetBitmap((int)window.ActualWidth,(int)window.ActualHeight,96,96,PixelFormats.Pbgra32);
        bitmap.Render(window);var pixel=new byte[4];
        bitmap.CopyPixels(new Int32Rect(20,Math.Max(1,(int)window.ActualHeight-20),1,1),pixel,4,0);
        return pixel[3];
    }
}
