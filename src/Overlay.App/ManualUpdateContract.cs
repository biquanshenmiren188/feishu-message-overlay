using System.IO;
using System.Text.Json;
using System.Windows;
using Overlay.Core;

namespace Overlay.App;

public partial class MainWindow
{
    private sealed class ManualUpdateTransportFixture : IDesktopUpdateTransport
    {
        internal int Checks,Downloads;
        internal readonly TaskCompletionSource<(string Json,bool Private)> Response=new();
        public Task<(string Json,bool Private)> LatestAsync(CancellationToken ct){Checks++;return Response.Task;}
        public async Task DownloadAsync(DesktopRelease release,bool isPrivate,string zip,CancellationToken ct){Downloads++;await File.WriteAllTextAsync(zip,"invalid synthetic package",ct);}
        public void Dispose(){}
    }
    private async Task RunManualUpdateContractAsync(string output)
    {
        var folder=Path.Combine(output,"manual-update-contract");Directory.CreateDirectory(folder);
        var statePath=Path.Combine(folder,"state.json");
        File.WriteAllText(statePath,"{\"Enabled\":true}");
        var fixture=new ManualUpdateTransportFixture();
        using var updater=new DesktopAutoUpdate(this,fixture,folder);
        var checks=new List<string>();
        void Check(bool value,string name){if(!value)throw new InvalidOperationException(name);checks.Add(name);}
        Check(!updater.Enabled&&!JsonSerializer.Deserialize<DesktopUpdateState>(File.ReadAllText(statePath))!.Enabled,"legacy automatic preference migrated off");
        await Task.Delay(250);
        Check(fixture.Checks==0&&fixture.Downloads==0,"startup performs no update network requests");
        Check(!updater.CanInstall,"install disabled before finding a release");
        var checking=updater.CheckAsync();await updater.CheckAsync();
        Check(updater.Busy&&fixture.Checks==1,"repeated manual clicks coalesce during check");
        const string tag="v2099.01.01.1";
        var asset=$"FeishuMessageOverlay-{tag}-win-x64.zip";
        fixture.Response.SetResult((JsonSerializer.Serialize(new{draft=false,prerelease=false,tag_name=tag,assets=new[]{new{name=asset,state="uploaded",size=50,digest="sha256:"+new string('0',64),browser_download_url=$"https://github.com/{DesktopUpdates.Repository}/releases/download/{tag}/{asset}"}}}),true));
        await checking;
        Check(fixture.Downloads==0&&updater.CanInstall&&!updater.Busy,"checking a newer release does not download it");
        var dialog=new Window{ShowActivated=false,ShowInTaskbar=false,Left=-20000,Top=-20000,Width=1,Height=1,WindowStyle=WindowStyle.None};
        dialog.Show();
        try{await updater.InstallManuallyAsync();Check(fixture.Downloads==0,"visible dialog blocks installation");}
        finally{dialog.Close();}
        await updater.InstallManuallyAsync();
        Check(fixture.Downloads==1&&!updater.Busy&&!exiting,"explicit install downloads but corrupt package never exits app");
        await Task.Delay(250);
        Check(fixture.Downloads==1&&fixture.Checks==1,"failure never automatically retries");
        File.WriteAllText(Path.Combine(output,"manual-update-contract.json"),JsonSerializer.Serialize(new{passed=true,checks,realNetwork=false}));
    }
}
