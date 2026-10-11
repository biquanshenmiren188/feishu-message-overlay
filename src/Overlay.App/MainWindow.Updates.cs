using System.Windows;
using System.Windows.Input;
namespace Overlay.App;

public partial class MainWindow
{
    private DesktopAutoUpdate? desktopUpdates;
    internal bool CanApplyDesktopUpdate=>!exiting&&settingsWindow?.IsVisible!=true&&Mouse.LeftButton==MouseButtonState.Released&&Mouse.RightButton==MouseButtonState.Released
        &&Application.Current.Windows.Cast<Window>().All(w=>w==this||!w.IsVisible);
    internal void StartDesktopUpdates()
    {
        if(App.SmokeMode)return;
        try{desktopUpdates=new(this);}catch{SetStatus("自动更新暂不可用，当前程序继续运行");}
    }
    private void AddUpdateMenu(System.Windows.Forms.ContextMenuStrip menu)
    {
        var version=new System.Windows.Forms.ToolStripMenuItem("版本 "+DesktopAutoUpdate.CurrentVersion){Enabled=false};
        var status=new System.Windows.Forms.ToolStripMenuItem("等待检查更新"){Enabled=false};
        var automatic=new System.Windows.Forms.ToolStripMenuItem("自动更新（空闲时安装）");
        automatic.Click+=(_,_)=>Dispatcher.Invoke(()=>{try{desktopUpdates?.SetEnabled(!(desktopUpdates?.Enabled??false));}catch{SetStatus("更新设置保存失败");}});
        var check=new System.Windows.Forms.ToolStripMenuItem("立即检查更新");
        check.Click+=async(_,_)=>{if(desktopUpdates is not null)await Dispatcher.InvokeAsync(()=>desktopUpdates.CheckAsync(true)).Task.Unwrap();};
        menu.Opening+=(_,_)=>{automatic.Checked=desktopUpdates?.Enabled??false;status.Text=desktopUpdates?.Status??"自动更新尚未就绪";};
        menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());menu.Items.AddRange([version,status,automatic,check]);
    }
}
