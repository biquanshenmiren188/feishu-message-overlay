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
        try{desktopUpdates=new(this);desktopUpdates.Changed+=RefreshUpdateMenu;RefreshUpdateMenu();}catch{SetStatus("手动更新暂不可用，当前程序继续运行");}
    }
    private System.Windows.Forms.ToolStripMenuItem? updateStatusItem,updateCheckItem,updateInstallItem;
    private void RefreshUpdateMenu()
    {
        if(updateStatusItem is not null)updateStatusItem.Text=desktopUpdates?.Status??"仅手动更新";
        if(updateCheckItem is not null)updateCheckItem.Enabled=desktopUpdates is {Busy:false};
        if(updateInstallItem is not null)updateInstallItem.Enabled=desktopUpdates?.CanInstall??false;
    }
    private void AddUpdateMenu(System.Windows.Forms.ContextMenuStrip menu)
    {
        var version=new System.Windows.Forms.ToolStripMenuItem("版本 "+DesktopAutoUpdate.CurrentVersion){Enabled=false};
        updateStatusItem=new("仅手动更新"){Enabled=false};
        updateCheckItem=new("检查更新");
        updateInstallItem=new("下载并安装更新（重启小窗）"){Enabled=false};
        updateCheckItem.Click+=async(_,_)=>{if(desktopUpdates is not null)await Dispatcher.InvokeAsync(()=>desktopUpdates.CheckAsync()).Task.Unwrap();};
        updateInstallItem.Click+=async(_,_)=>{if(desktopUpdates is not null)await Dispatcher.InvokeAsync(()=>desktopUpdates.InstallManuallyAsync()).Task.Unwrap();};
        menu.Opening+=(_,_)=>RefreshUpdateMenu();
        menu.Items.Add(new System.Windows.Forms.ToolStripSeparator());menu.Items.AddRange([version,updateStatusItem,updateCheckItem,updateInstallItem]);
    }
}
