using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Windows.Threading;
using Overlay.Core;

namespace Overlay.App;

internal sealed record DesktopUpdateState(bool Enabled=true,DateTimeOffset NextCheck=default,string? FailedTag=null,string Status="等待检查");
internal sealed record DesktopUpdatePlan(string Install,string Package,string Tag,string Zip,string Hash,long Size,int OldPid,long OldStartTicks,string Receipt,bool Background,string StatePath);

internal sealed class DesktopAutoUpdate : IDisposable
{
    internal static string CurrentVersion=>typeof(App).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().First(a=>a.Key=="UpdateVersion").Value!;
    private readonly MainWindow window;
    private readonly DispatcherTimer timer=new(){Interval=TimeSpan.FromMinutes(1)};
    private readonly CancellationTokenSource stop=new();
    private readonly string directory=Path.Combine(LocalStorage.DirectoryPath,"updates");
    private readonly GitHubUpdateTransport transport=new();
    private DesktopUpdateState state;
    private DesktopUpdatePlan? prepared;
    private bool busy;
    internal bool Enabled=>state.Enabled;
    internal string Status=>state.Status;
    private string StatePath=>Path.Combine(directory,"state.json");
    internal DesktopAutoUpdate(MainWindow window)
    {
        this.window=window;
        try{state=File.Exists(StatePath)?JsonSerializer.Deserialize<DesktopUpdateState>(File.ReadAllText(StatePath))??new(false):new();}
        catch{state=new(false,Status:"更新配置不可读，请手动检查");}
        timer.Tick+=async(_,_)=>{await CheckAsync(false);await ApplyWhenIdleAsync();};timer.Start();
        _=CheckAsync(false);
    }
    private void Save(){LocalStorage.AtomicWrite(StatePath,JsonSerializer.SerializeToUtf8Bytes(state));}
    internal void SetEnabled(bool enabled){var previous=state;try{state=state with{Enabled=enabled};Save();}catch{state=previous;throw;}}
    internal async Task CheckAsync(bool manual)
    {
        if(busy||stop.IsCancellationRequested||(!manual&&(!state.Enabled||state.NextCheck>DateTimeOffset.UtcNow))||prepared is not null)return;
        busy=true;
        try
        {
            state=state with{Status="正在检查更新",NextCheck=DateTimeOffset.UtcNow.AddHours(1)};Save();
            var metadata=await transport.LatestAsync(stop.Token);
            var release=DesktopUpdates.SelectRelease(metadata.Json,CurrentVersion);
            if(release is null){state=state with{Status="已是最新版本",NextCheck=DateTimeOffset.UtcNow.AddHours(6)};Save();return;}
            if(!manual&&state.FailedTag==release.Tag){state=state with{Status="此版本更新失败，保留旧版；可手动重试",NextCheck=DateTimeOffset.UtcNow.AddHours(6)};Save();return;}
            state=state with{Status="正在下载 "+release.Tag};Save();
            var session=Path.Combine(directory,Guid.NewGuid().ToString("N"));Directory.CreateDirectory(session);
            var zip=Path.Combine(session,"package.zip");
            await transport.DownloadAsync(release,metadata.Private,zip,stop.Token);
            var package=Path.Combine(session,"package");
            await Task.Run(()=>DesktopUpdates.ExtractVerified(zip,package,release.Tag,release.Sha256,release.Size),stop.Token);
            using var self=Process.GetCurrentProcess();
            prepared=new(AppContext.BaseDirectory,package,release.Tag,zip,release.Sha256,release.Size,self.Id,self.StartTime.ToUniversalTime().Ticks,Path.Combine(session,"healthy.json"),!window.IsVisible,StatePath);
            state=state with{Status=release.Tag+(Enabled?" 已就绪，空闲时自动安装":" 已就绪，开启自动更新后安装")};Save();
        }
        catch(OperationCanceledException){if(!stop.IsCancellationRequested){state=state with{Status="更新检查超时，稍后自动重试"};try{Save();}catch{}}}
        catch{state=state with{Status="更新检查或校验失败；请检查网络及 GitHub 登录，当前版本继续运行"};try{Save();}catch{}}
        finally{busy=false;}
    }
    [StructLayout(LayoutKind.Sequential)]private struct LastInput{public uint Size;public uint Tick;}
    [DllImport("user32.dll")]private static extern bool GetLastInputInfo(ref LastInput input);
    private static bool Idle(){var input=new LastInput{Size=(uint)Marshal.SizeOf<LastInput>()};return GetLastInputInfo(ref input)&&unchecked((uint)Environment.TickCount-input.Tick)>=30000;}
    private async Task ApplyWhenIdleAsync()
    {
        if(busy||prepared is null||!Enabled||!Idle()||!window.CanApplyDesktopUpdate)return;
        busy=true;
        try
        {
            if(!window.FlushForSessionEnding())return;
            var plan=prepared with{Background=!window.IsVisible};
            var session=Path.GetDirectoryName(plan.Zip)!;var runner=Path.Combine(session,"runner");Directory.CreateDirectory(runner);
            // Run the current trusted updater from outside the directory being replaced.
            foreach(var file in Directory.EnumerateFiles(AppContext.BaseDirectory).Where(p=>Path.GetFileName(p)=="FeishuMessageOverlay.exe"||p.EndsWith(".dll",StringComparison.OrdinalIgnoreCase)||p.EndsWith(".runtimeconfig.json")||p.EndsWith(".deps.json")))File.Copy(file,Path.Combine(runner,Path.GetFileName(file)),true);
            var planPath=Path.Combine(session,"plan.json");LocalStorage.AtomicWrite(planPath,JsonSerializer.SerializeToUtf8Bytes(plan));
            var start=new ProcessStartInfo(Path.Combine(runner,"FeishuMessageOverlay.exe")){UseShellExecute=false,CreateNoWindow=true,WorkingDirectory=runner};
            start.ArgumentList.Add("--apply-desktop-update");start.ArgumentList.Add(planPath);
            if(Process.Start(start) is null)throw new IOException("Updater did not start");
            ProcessLifecycle.ExitReason="automatic_update";await window.ExitAsync();
        }
        catch{state=state with{Status="无法安装更新，当前版本继续运行",FailedTag=prepared.Tag};prepared=null;try{Save();}catch{}}
        finally{busy=false;}
    }
    public void Dispose(){timer.Stop();stop.Cancel();transport.Dispose();}

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
        LocalStorage.AtomicWrite(plan.StatePath,JsonSerializer.SerializeToUtf8Bytes(state with{FailedTag=success?null:plan.Tag,Status=status??(success?"已更新到 "+plan.Tag:"更新失败，已恢复旧版"),NextCheck=DateTimeOffset.UtcNow.AddHours(6)}));
    }
    internal static void WriteHealthReceipt(string path)
    {
        // Receipt paths must be inside this user's updater workspace, never arbitrary files.
        var root=Path.GetFullPath(Path.Combine(LocalStorage.DirectoryPath,"updates"))+Path.DirectorySeparatorChar;
        var full=Path.GetFullPath(path);
        if(full.StartsWith(root,StringComparison.OrdinalIgnoreCase)&&Path.GetFileName(full)=="healthy.json")LocalStorage.AtomicWrite(full,JsonSerializer.SerializeToUtf8Bytes(new{pid=Environment.ProcessId,version=CurrentVersion}));
    }
}
