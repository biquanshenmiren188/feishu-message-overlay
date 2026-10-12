using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Overlay.App;

// Fill down beside the message pane, then continue in a new column to its left.
// Beyond the monitor's width budget, retain every item in the scrollable last column.
public sealed class OpportunityColumnsPanel : Panel
{
    internal const double CardWidth=320;
    private readonly List<Rect> positions=[];
    private int columns=1;
    protected override Size MeasureOverride(Size available)
    {
        DependencyObject? ancestor=VisualTreeHelper.GetParent(this);
        while(ancestor is not null && ancestor is not OpportunityBoard)ancestor=VisualTreeHelper.GetParent(ancestor);
        var board=ancestor as OpportunityBoard;
        var height=Math.Max(120,board?.ActualHeight??600);
        var maxColumns=board?.MaximumColumns??1;
        positions.Clear();double y=0,maxHeight=0;var column=0;
        foreach(UIElement child in InternalChildren)
        {
            child.Measure(new Size(CardWidth,double.PositiveInfinity));
            var itemHeight=Math.Ceiling(child.DesiredSize.Height);
            if(y>0 && y+itemHeight>height && column+1<maxColumns){column++;y=0;}
            positions.Add(new Rect(column*CardWidth,y,CardWidth,itemHeight));
            y+=itemHeight;maxHeight=Math.Max(maxHeight,y);
        }
        columns=column+1;board?.ReportColumns(columns);
        return new Size(columns*CardWidth,maxHeight);
    }
    protected override Size ArrangeOverride(Size finalSize)
    {
        for(var i=0;i<InternalChildren.Count;i++)
        {
            var p=positions[i];
            p.X=(columns-1)*CardWidth-p.X;
            InternalChildren[i].Arrange(p);
        }
        return finalSize;
    }
}
