using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    private bool contentLayoutPending;
    private string? alignAfterLayout;
    // Coalesce data, width and font changes into one layout pass. No idle polling.
    private void RequestContentLayout(string? align=null)
    {
        if(align is not null)alignAfterLayout=align;
        if(contentLayoutPending || !ready)return;
        contentLayoutPending=true;
        Dispatcher.BeginInvoke(()=>
        {
            try
            {
                UpdateLayout();
                if(initialFit && (!App.SmokeMode || verifyContentFit))MeasureContentHeight();
                UpdateLayout();
                if(alignAfterLayout is {} id)
                {
                    var item=displayed.FirstOrDefault(m=>m.Id==id);
                    if(item is not null && MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el)
                    {
                        synchronizingScroll=true;
                        var top=el.TranslatePoint(new Point(),MessageScroll).Y+MessageScroll.VerticalOffset;
                        MessageScroll.ScrollToVerticalOffset(Math.Min(top,MessageScroll.ScrollableHeight));UpdateLayout();
                    }
                }
            }
            finally{alignAfterLayout=null;contentLayoutPending=false;synchronizingScroll=false;ScheduleReading();}
        },DispatcherPriority.Loaded);
    }
    private bool verifyContentFit;
    private double MeasureCard(IncomingMessage item,double width)
    {
        var presenter=new ContentPresenter{Content=item,ContentTemplate=MessageList.ItemTemplate};
        presenter.SetValue(System.Windows.Documents.TextElement.FontFamilyProperty,MessageList.FontFamily);
        presenter.SetValue(System.Windows.Documents.TextElement.FontSizeProperty,MessageList.FontSize);
        presenter.Measure(new Size(Math.Max(1,width),double.PositiveInfinity));
        return presenter.DesiredSize.Height;
    }
    private void MeasureContentHeight()
    {
        var work=CurrentWorkArea();UpdateLayout();
        var width=MessageScroll.ViewportWidth>0?MessageScroll.ViewportWidth:Math.Max(1,ActualWidth-11);
        var ordinary=displayed.Sum(item=>MeasureCard(item,width));
        var pin=pinnedLatest is null || PinnedArea.Visibility!=Visibility.Visible?0:MeasureCard(pinnedLatest,Math.Max(1,PinnedArea.ActualWidth));
        // Extremely long pinned content has its own scroll viewport; never compress ordinary text.
        var pinLimit=Math.Max(32,(work.Height-36)*.4);
        PinnedArea.MaxHeight=Math.Min(pin,pinLimit);
        var desired=ordinary+Math.Min(pin,pinLimit)+35+(pin>0?4:0);
        fittingWindow=true;
        try{Height=Math.Clamp(desired,MinHeight,Math.Max(MinHeight,work.Height));}
        finally{fittingWindow=false;}
    }
    private double CurrentBottomRemaining()
    {
        var item=displayed.FirstOrDefault(m=>m.Id==reader.Current);
        if(item is null || MessageList.ItemContainerGenerator.ContainerFromItem(item) is not FrameworkElement el)return 0;
        return Math.Max(0,el.TranslatePoint(new Point(0,el.ActualHeight),MessageScroll).Y-MessageScroll.ViewportHeight);
    }
    private void ReadingTick()
    {
        readingTimer.Stop();
        if(contentLayoutPending || followingPaused || !IsVisible || AutoScroll.IsChecked!=true){ScheduleReading();return;}
        UpdateLayout();var remaining=CurrentBottomRemaining();var now=DateTimeOffset.UtcNow;
        if(remaining>1 && MessageScroll.VerticalOffset<MessageScroll.ScrollableHeight-.5)
        {
            // Read each viewport of a long body for a full dwell interval before advancing its ID.
            synchronizingScroll=true;
            MessageScroll.ScrollToVerticalOffset(MessageScroll.VerticalOffset+Math.Min(remaining,Math.Max(20,MessageScroll.ViewportHeight-40)));
            UpdateLayout();synchronizingScroll=false;reader.Focus(reader.Current,now);
        }
        else
        {
            var id=reader.Advance(now,true,false);
            if(id is not null)ShowReadingMessage(id);
        }
        ScheduleReading();
    }
}
