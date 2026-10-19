using System.Windows;
using System.Windows.Input;
using System.Windows.Controls.Primitives;
using System.Windows.Threading;
namespace Overlay.App;
public partial class MainWindow
{
    private DispatcherTimer? bottomAlignmentTimer;
    private bool aligningBottom;
    private double bottomScrollDirection=1;
    private void QueueBottomAlignment(double change)
    {
        if(aligningBottom || !ready || exiting)return;
        if(Math.Abs(change)>.01)bottomScrollDirection=change;
        if(bottomAlignmentTimer is null)
        {
            bottomAlignmentTimer=new DispatcherTimer(DispatcherPriority.Background,Dispatcher){Interval=TimeSpan.FromMilliseconds(140)};
            bottomAlignmentTimer.Tick+=(_,_)=>
            {
                if(Mouse.Captured is Thumb || contentLayoutPending)return;
                bottomAlignmentTimer.Stop();
                if(!exiting)AlignBottomMessage();
            };
        }
        bottomAlignmentTimer.Stop();bottomAlignmentTimer.Start();
    }
    private void AlignBottomMessage()
    {
        UpdateLayout();
        var viewport=MessageScroll.ViewportHeight;
        if(viewport<=0 || (MessageScroll.VerticalOffset<=.5 && bottomScrollDirection<0) || MessageScroll.ScrollableHeight-MessageScroll.VerticalOffset<=.5)return;
        foreach(var item in displayed)
        {
            if(MessageList.ItemContainerGenerator.ContainerFromItem(item) is not FrameworkElement element)continue;
            var top=element.TranslatePoint(new Point(),MessageScroll).Y;
            var bottom=top+element.ActualHeight;
            if(top>=viewport-.5 || bottom<=viewport+.5)continue;
            // Oversized messages remain freely scrollable; never skip their content.
            if(element.ActualHeight>viewport)return;
            var edge=bottomScrollDirection<0?top:bottom;
            aligningBottom=true;
            try
            {
                MessageScroll.ScrollToVerticalOffset(Math.Clamp(MessageScroll.VerticalOffset+edge-viewport,0,MessageScroll.ScrollableHeight));
                UpdateLayout();
            }
            finally{aligningBottom=false;}
            return;
        }
    }
}
