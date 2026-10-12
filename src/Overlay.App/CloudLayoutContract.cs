using System.IO;
using System.Text.Json;
using System.Windows;
namespace Overlay.App;
public partial class MainWindow
{
    private static void RunCloudLayoutContract(string output)
    {
        var originalPath=Preferences.ContractPath;
        Preferences.ContractPath=Path.Combine(output,"cloud-layout-preferences.json");
        try
        {
            // This is the real legacy saved width observed before the upgrade: 300 + 360.
            _=Preferences.Load();if(!new Preferences{Width=660,Height=752,FontSize=13,Opacity=.95}.Save())throw new IOException("Synthetic layout save failed");
            var passes=new List<object>();
            for(var restart=0;restart<3;restart++)
            {
                var window=new MainWindow();
                try
                {
                    window.EnableOpportunityBoard();
                    var expected=restart==2?676:616;
                    if(Math.Abs(window.Width-expected)>.01 || window.FontScale.Value!=13 || window.OpacityScale.Value!=95)throw new InvalidOperationException("Cloud restart changed saved layout");
                    window.EnableOpportunityBoard();if(Math.Abs(window.Width-expected)>.01)throw new InvalidOperationException("Repeated connection widened layout");
                    passes.Add(new{restart,totalWidth=window.Width,textWidth=window.Width-window.CardsColumn.Width.Value});
                    if(restart==1)window.Width=676; // A real user resize must round-trip too.
                    if(!window.FlushForSessionEnding())throw new IOException("Layout flush failed");
                    if(Preferences.Load().MessagePaneWidth!=(restart>=1?420:360))throw new InvalidOperationException("Text pane width not saved independently");
                }
                finally{window.exiting=true;window.Close();window.audio.Dispose();window.preferenceTimer.Stop();}
            }
            File.WriteAllText(Path.Combine(output,"cloud-layout-contract.json"),JsonSerializer.Serialize(new{passed=true,passes,legacyMigrated=true,customResizeRetained=true,fontsUnchanged=true}));
        }
        finally{Preferences.ContractPath=originalPath;_=Preferences.Load();}
    }
}
