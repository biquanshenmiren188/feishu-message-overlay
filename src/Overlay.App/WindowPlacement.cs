using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
namespace Overlay.App;
internal static class WindowPlacement
{
    [StructLayout(LayoutKind.Sequential)]private struct Rect{public int Left,Top,Right,Bottom;}
    [DllImport("user32.dll")]private static extern bool GetWindowRect(nint h,out Rect r);
    [DllImport("user32.dll")]private static extern uint GetDpiForWindow(nint h);
    [DllImport("user32.dll")]private static extern bool SetWindowPos(nint h,nint after,int x,int y,int w,int height,uint flags);
    internal static void TopRight(Window window)
    {
        var hwnd=new WindowInteropHelper(window).Handle;if(hwnd==0)return;
        var work=System.Windows.Forms.Screen.FromHandle(hwnd).WorkingArea;
        if(!GetWindowRect(hwnd,out var rect))return;
        SetWindowPos(hwnd,0,work.Right-(rect.Right-rect.Left),work.Top,0,0,0x15);
    }
    internal static object Snapshot(Window window)
    {
        var hwnd=new WindowInteropHelper(window).Handle;GetWindowRect(hwnd,out var rect);
        var work=System.Windows.Forms.Screen.FromHandle(hwnd).WorkingArea;
        return new{dpi=GetDpiForWindow(hwnd),left=rect.Left,top=rect.Top,width=rect.Right-rect.Left,height=rect.Bottom-rect.Top,workLeft=work.Left,workTop=work.Top,workRight=work.Right,workBottom=work.Bottom,rightMargin=work.Right-rect.Right,topMargin=rect.Top-work.Top};
    }
}
