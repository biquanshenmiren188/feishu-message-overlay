using System.Windows;
using System.Windows.Automation;
namespace Overlay.App;

public partial class MainWindow
{
    private void UpdateHistoryButton()
    {
        HistoryButton.IsEnabled=readingQueue.Length>0;
        HistoryLabel.Text=browsingHistory?"最新":"历史";
        HistoryButton.ToolTip=browsingHistory
            ?$"正在查看历史（已保留 {readingQueue.Length} 条），轮播暂停；点击回到最新消息"
            :$"查看本次运行已收到的推送（已保留 {readingQueue.Length} 条，最多100条）；滚轮翻阅，不因时间自动清空";
        AutomationProperties.SetName(HistoryButton,browsingHistory?"返回最新推送":"查看推送历史");
    }
    private void HistoryClick(object sender,RoutedEventArgs e)
    {
        if(readingQueue.Length==0)return;
        browsingHistory=!browsingHistory;followingPaused=browsingHistory;
        focusCloudLatest=false;readingTimer.Stop();readingIdleTimer.Stop();
        var index=browsingHistory?0:Math.Max(0,readingQueue.Length-3);
        rangeStart=readingQueue[index].Id;reader.Focus(rangeStart,DateTimeOffset.UtcNow);
        DisplayRange(rangeStart,true);RequestContentLayout(rangeStart);UpdateHistoryButton();ScheduleReading();
    }
}
