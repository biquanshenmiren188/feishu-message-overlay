using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using Overlay.Core;

namespace Overlay.App;

internal sealed record DesktopUpdateState(bool Enabled=false,DateTimeOffset NextCheck=default,string? FailedTag=null,string Status="仅手动更新，请点击检查更新");
internal sealed record DesktopUpdatePlan(string Install,string Package,string Tag,string Zip,string Hash,long Size,int OldPid,long OldStartTicks,string Receipt,bool Background,string StatePath);

internal sealed class DesktopAutoUpdate : IDisposable
{
    internal static string CurrentVersion=>typeof(App).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().First(a=>a.Key=="UpdateVersion").Value!;
    private readonly MainWindow window;
    private readonly CancellationTokenSource stop=new();
    private readonly string directory;
    private readonly IDesktopUpdateTransport transport;
    private DesktopUpdateState state;
    private DesktopUpdatePlan? prepared;
    private DesktopRelease? available;
    private bool privateRelease;
    private bool busy;
    internal bool Enabled=>false;
    internal bool Busy=>busy;
    internal bool CanInstall=>!busy&&available is not null;
    internal event Action? Changed;
    internal string Status=>state.Status;
    private string StatePath=>Path.Combine(directory,"state.json");
    internal DesktopAutoUpdate(MainWindow window,IDesktopUpdateTransport? transport=null,string? updateDirectory=null)
    {
        this.window=window;
        this.transport=transport??new GitHubUpdateTransport();
        directory=updateDirectory??Path.Combine(LocalStorage.DirectoryPath,"updates");
        try{state=File.Exists(StatePath)?JsonSerializer.Deserialize<DesktopUpdateState>(File.ReadAllText(StatePath))??new(false):new();}
        catch{state=new(false,Status:"更新配置不可读，请手动检查");}
        // Migrate legacy opt-in state. Startup never checks, downloads or installs.
        state=state with{Enabled=false,NextCheck=default,Status="仅手动更新，请点击检查更新"};Save();
    }
    private void Save(){LocalStorage.AtomicWrite(StatePath,JsonSerializer.SerializeToUtf8Bytes(state));Changed?.Invoke();}
    internal async Task CheckAsync()
    {
        if(busy||stop.IsCancellationRequested||prepared is not null)return;
        busy=true;
        try
        {
            available=null;
            state=state with{Status="正在检查更新"};Save();
            var metadata=await transport.LatestAsync(stop.Token);
            available=DesktopUpdates.SelectRelease(metadata.Json,CurrentVersion);privateRelease=metadata.Private;
            state=state with{Status=available is null?"已是最新版本":$"发现 {available.Tag}，请点击下载并安装"};Save();
        }
        catch(OperationCanceledException){if(!stop.IsCancellationRequested){state=state with{Status="更新检查超时，请手动重试"};try{Save();}catch{}}}
        catch{state=state with{Status="更新检查或校验失败；请检查网络及 GitHub 登录，当前版本继续运行"};try{Save();}catch{}}
        finally{busy=false;Changed?.Invoke();}
    }
    internal async Task InstallManuallyAsync()
    {
        if(!CanInstall||stop.IsCancellationRequested)return;
        if(!window.CanApplyDesktopUpdate){state=state with{Status="请关闭设置或其他对话框后，再点击安装"};Save();return;}
        busy=true;
        try
        {
            if(prepared is null)
            {
                var release=available!;
                state=state with{Status="正在下载并校验 "+release.Tag};Save();
                var sessionPath=Path.Combine(directory,Guid.NewGuid().ToString("N"));Directory.CreateDirectory(sessionPath);
                var zip=Path.Combine(sessionPath,"package.zip");
                await transport.DownloadAsync(release,privateRelease,zip,stop.Token);
                var package=Path.Combine(sessionPath,"package");
                await Task.Run(()=>DesktopUpdates.ExtractVerified(zip,package,release.Tag,release.Sha256,release.Size),stop.Token);
                using var self=Process.GetCurrentProcess();
                prepared=new(AppContext.BaseDirectory,package,release.Tag,zip,release.Sha256,release.Size,self.Id,self.StartTime.ToUniversalTime().Ticks,Path.Combine(sessionPath,"healthy.json"),!window.IsVisible,StatePath);
            }
            // User may have opened settings during the download; require another click then.
            if(!window.CanApplyDesktopUpdate){state=state with{Status="下载已完成，请关闭设置后再次点击安装"};Save();return;}
            if(!window.FlushForSessionEnding()){state=state with{Status="设置保存失败，请处理后再次点击安装"};Save();return;}
            var plan=prepared with{Background=!window.IsVisible};
            var session=Path.GetDirectoryName(plan.Zip)!;var runner=Path.Combine(session,"runner");Directory.CreateDirectory(runner);
            // Run the current trusted updater from outside the directory being replaced.
            foreach(var file in Directory.EnumerateFiles(AppContext.BaseDirectory).Where(p=>Path.GetFileName(p)=="FeishuMessageOverlay.exe"||p.EndsWith(".dll",StringComparison.OrdinalIgnoreCase)||p.EndsWith(".runtimeconfig.json")||p.EndsWith(".deps.json")))File.Copy(file,Path.Combine(runner,Path.GetFileName(file)),true);
            var planPath=Path.Combine(session,"plan.json");LocalStorage.AtomicWrite(planPath,JsonSerializer.SerializeToUtf8Bytes(plan));
            var start=new ProcessStartInfo(Path.Combine(runner,"FeishuMessageOverlay.exe")){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=runner};
            start.ArgumentList.Add("--apply-desktop-update");start.ArgumentList.Add(planPath);
            if(Process.Start(start) is null)throw new IOException("Updater did not start");
            ProcessLifecycle.ExitReason="manual_update";await window.ExitAsync();
        }
        catch{state=state with{Status="下载、校验或安装失败，当前版本继续运行；可手动重试",FailedTag=available?.Tag};prepared=null;try{Save();}catch{}}
        finally{busy=false;Changed?.Invoke();}
    }
    public void Dispose(){stop.Cancel();transport.Dispose();}

    internal static async Task<int> RunInstallerAsync(string planPath)
    {
        DesktopUpdatePlan? plan=null;var oldStopped=false;var restartAttempted=false;string? originalHash=null;
        try
        {
            plan=JsonSerializer.Deserialize<DesktopUpdatePlan>(File.ReadAllText(planPath))??throw new IOException("Missing plan");
            _=DesktopUpdates.ParseVersion(plan.Tag);
            var session=Path.GetFullPath(Path.GetDirectoryName(planPath)!);
            if(Path.GetFullPath(plan.Zip)!=Path.Combine(session,"package.zip")||Path.GetFullPath(plan.Package)!=Path.Combine(session,"package")||Path.GetFullPath(plan.Receipt)!=Path.Combine(session,"healthy.json")||Path.GetFullPath(plan.StatePath)!=Path.Combine(Directory.GetParent(session)!.FullName,"state.json"))throw new IOException("Invalid transaction paths");
            var install=Path.GetFullPath(plan.Install).TrimEnd(Path.DirectorySeparatorChar);
            using(var original=File.OpenRead(Path.Combine(install,"FeishuMessageOverlay.exe")))originalHash=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(original));
            if(session.StartsWith(install+Path.DirectorySeparatorChar,StringComparison.OrdinalIgnoreCase))throw new IOException("Updater must run outside application directory");
            using var transaction=new FileStream(Path.Combine(Path.GetDirectoryName(plan.StatePath)!,"install.lock"),FileMode.OpenOrCreate,FileAccess.ReadWrite,FileShare.None);
            try
            {
                using var old=Process.GetProcessById(plan.OldPid);
                if(old.StartTime.ToUniversalTime().Ticks!=plan.OldStartTicks||!string.Equals(old.MainModule?.FileName,Path.Combine(install,"FeishuMessageOverlay.exe"),StringComparison.OrdinalIgnoreCase))throw new IOException("Application process changed");
                using var wait=new CancellationTokenSource(TimeSpan.FromSeconds(60));await old.WaitForExitAsync(wait.Token);
            }
            catch(ArgumentException){} // The expected process has already exited.
            oldStopped=true;
            if(new FileInfo(plan.Zip).Length!=plan.Size||plan.Size>DesktopUpdates.MaximumDownload)throw new IOException("Invalid package size");
            DesktopUpdates.VerifyHash(plan.Zip,plan.Hash);DesktopUpdates.VerifyDirectory(plan.Package,plan.Tag);
            var result=await DesktopUpdates.InstallAsync(install,plan.Package,plan.Tag,async path=>
            {
                using var process=StartInstalled(path,plan);
                var healthy=false;
                try
                {
                var deadline=DateTime.UtcNow.AddSeconds(60);
                while(!process.HasExited&&DateTime.UtcNow<deadline)
                {
                    if(File.Exists(plan.Receipt))
                    {
                        using var receipt=JsonDocument.Parse(File.ReadAllText(plan.Receipt));
                        if(receipt.RootElement.GetProperty("pid").GetInt32()==process.Id&&receipt.RootElement.GetProperty("version").GetString()==plan.Tag)
                        {await Task.Delay(5000);if(!process.HasExited){WriteResult(plan,true);healthy=true;return true;}break;}
                    }
                    await Task.Delay(500);
                }
                return false;
                }
                finally{if(!healthy&&!process.HasExited){process.Kill();await process.WaitForExitAsync();}}
            },path=>{WriteResult(plan,false);restartAttempted=true;using var restored=StartInstalled(path,plan with{Receipt=""});return Task.CompletedTask;});
            return result?0:1;
        }
        catch(Exception error)
        {
            if(plan is not null){try{
                LocalStorage.AtomicWrite(Path.Combine(Path.GetDirectoryName(planPath)!,"failure.json"),JsonSerializer.SerializeToUtf8Bytes(new{type=error.GetType().Name,error.HResult}));
                WriteResult(plan,false,"更新未完成，请检查旧版备份");
                if(oldStopped&&!restartAttempted&&originalHash is not null){DesktopUpdates.VerifyHash(Path.Combine(plan.Install,"FeishuMessageOverlay.exe"),originalHash);using var restored=StartInstalled(plan.Install,plan with{Receipt=""});}
            }catch{}}
            return 1;
        }
    }
    private static Process StartInstalled(string directory,DesktopUpdatePlan plan)
    {
        var start=new ProcessStartInfo(Path.Combine(directory,"FeishuMessageOverlay.exe")){UseShellExecute=false,WorkingDirectory=directory};
        if(plan.Background)start.ArgumentList.Add("--background");
        if(plan.Receipt.Length>0){start.ArgumentList.Add("--update-health-receipt");start.ArgumentList.Add(plan.Receipt);}
        return Process.Start(start)??throw new IOException("Application launch failed");
    }
    private static void WriteResult(DesktopUpdatePlan plan,bool success,string? status=null)
    {
        var state=JsonSerializer.Deserialize<DesktopUpdateState>(File.ReadAllText(plan.StatePath))??new();
        LocalStorage.AtomicWrite(plan.StatePath,JsonSerializer.SerializeToUtf8Bytes(state with{Enabled=false,FailedTag=success?null:plan.Tag,Status=status??(success?"已更新到 "+plan.Tag:"更新失败，已恢复旧版"),NextCheck=default}));
    }
    internal static void WriteHealthReceipt(string path)
    {
        // Receipt paths must be inside this user's updater workspace, never arbitrary files.
        var root=Path.GetFullPath(Path.Combine(LocalStorage.DirectoryPath,"updates"))+Path.DirectorySeparatorChar;
        var full=Path.GetFullPath(path);
        if(full.StartsWith(root,StringComparison.OrdinalIgnoreCase)&&Path.GetFileName(full)=="healthy.json")LocalStorage.AtomicWrite(full,JsonSerializer.SerializeToUtf8Bytes(new{pid=Environment.ProcessId,version=CurrentVersion}));
    }
}
