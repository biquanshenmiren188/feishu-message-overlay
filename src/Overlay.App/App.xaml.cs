using System.Windows;
using System.IO;
namespace Overlay.App;
public partial class App : Application
{
    private Mutex? instance;
    private EventWaitHandle? restoreSignal;
    private EventWaitHandle? snapshotSignal;
    private CancellationTokenSource? restoreStop;
    public static bool SmokeMode { get; private set; }
    public static string? SetupReceipt { get; private set; }
    internal static string SmokeStage { get; set; } = "ui";
    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        SmokeMode = e.Args.Contains("--smoke-test");
        if(e.Args.Contains("--browser-input-fixture"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            try{await BrowserInputFixture.RunAsync(e.Args.Last());Shutdown();}catch{Shutdown(1);}return;
        }
        if(e.Args.Contains("--drag-yield-fixture"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            try{await DragYieldFixture.RunAsync(e.Args.Last());Shutdown();}catch{Shutdown(1);}return;
        }
        if(e.Args.Contains("--audio-check"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--audio-check").Skip(1).ToArray();
            if(args.Length!=2){Shutdown(2);return;}
            var accepted=AlertAudio.PlayWave(args[0]);
            File.WriteAllText(args[1],System.Text.Json.JsonSerializer.Serialize(new{accepted,outputDevice=AlertAudio.HasOutputDevice}));
            await Task.Delay(900);Shutdown(accepted?0:1);return;
        }
        if(e.Args.Contains("--configure-audio"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--configure-audio").Skip(1).ToArray();
            if(args.Length!=2){Shutdown(2);return;}
            var saved=AlertAudio.IsSupported(args[0]) && (Preferences.Load() with {AudioPath=Path.GetFullPath(args[0])}).Save();
            File.WriteAllText(args[1],System.Text.Json.JsonSerializer.Serialize(new{saved}));Shutdown(saved?0:1);return;
        }
        if(e.Args.Contains("--configure-default-font"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var output=e.Args.SkipWhile(a=>a!="--configure-default-font").Skip(1).FirstOrDefault();if(output is null){Shutdown(2);return;}
            var present=System.Windows.Media.Fonts.SystemFontFamilies.Any(f=>f.Source=="Microsoft YaHei");
            var saved=present && (Preferences.Load() with {Font="Microsoft YaHei"}).Save();
            File.WriteAllText(output,System.Text.Json.JsonSerializer.Serialize(new{present,saved,font="Microsoft YaHei"}));Shutdown(saved?0:1);return;
        }
        if(e.Args.Contains("--diagnostic-contract-tests"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var diagnosticOutput=e.Args.SkipWhile(a=>a!="--diagnostic-contract-tests").Skip(1).First();
            try{await ConnectionDiagnostics.ContractAsync(diagnosticOutput);Shutdown();}catch{File.WriteAllText(diagnosticOutput,"FAIL diagnostic contract");Shutdown(1);}return;
        }
        if(e.Args.Contains("--resolve-group"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--resolve-group").Skip(1).ToArray();
            if(args.Length!=2){Shutdown(2);return;}
            var credentials=CredentialVault.LoadOnUserRequest();
            if(credentials is null){File.WriteAllText(args[1],"{\"state\":\"no_configuration\"}");Shutdown(1);return;}
            var match=await GroupDiscovery.FindAsync(credentials,args[0]);
            File.WriteAllText(args[1],System.Text.Json.JsonSerializer.Serialize(match));Shutdown();return;
        }
        if(e.Args.Contains("--select-authorized-groups"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--select-authorized-groups").Skip(1).ToArray();
            if(args.Length is <2 or >6){Shutdown(2);return;}
            var matches=new List<GroupDiscovery.Match>();
            foreach(var name in args.Skip(1))
            {
                var credentials=CredentialVault.LoadOnUserRequest();
                if(credentials is null){Shutdown(1);return;}
                matches.Add(await GroupDiscovery.FindAsync(credentials,name));
            }
            var joined=matches.Where(m=>m.State=="matched").Select(m=>m.ChatId!).Distinct().ToArray();
            var saved=false;var config=CredentialVault.LoadOnUserRequest();
            if(config is not null){if(joined.Length>0)saved=ConnectionSelection.Save(new ConnectionSettings{AppId=config.AppId,Secret=config.Secret,ChatIds=joined});config.Secret="";}
            File.WriteAllText(args[0],System.Text.Json.JsonSerializer.Serialize(new{saved,matches}));Shutdown(saved?0:1);return;
        }
        if(e.Args.Contains("--diagnose-saved"))
        {
            var arguments=e.Args.SkipWhile(a=>a!="--diagnose-saved").Skip(1).ToArray();
            if(arguments.Length!=2){Shutdown(2);return;}
            await ConnectionDiagnostics.RunAsync(arguments[0],arguments[1]);Shutdown();return;
        }
        ShutdownMode=ShutdownMode.OnExplicitShutdown;
        if(!SmokeMode)
        {
            var name="Local\\FeishuMessageOverlay-"+System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
            snapshotSignal=new EventWaitHandle(false,EventResetMode.AutoReset,name+"-snapshot");
            var snapshotPath=Path.Combine(Path.GetTempPath(),"FeishuMessageOverlay-diagnostic-"+System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value+".json");
            if(e.Args.Contains("--export-diagnostics"))
            {
                var output=e.Args.SkipWhile(a=>a!="--export-diagnostics").Skip(1).FirstOrDefault();
                if(output is null){Shutdown(2);return;}
                var started=DateTime.UtcNow;snapshotSignal.Set();
                for(var attempt=0;attempt<40;attempt++)
                {
                    await Task.Delay(100);
                    if(File.Exists(snapshotPath)&&File.GetLastWriteTimeUtc(snapshotPath)>=started)
                    {File.Copy(snapshotPath,output,true);File.Delete(snapshotPath);Shutdown();return;}
                }
                Shutdown(1);return;
            }
            instance=new Mutex(true,name,out var first);
            restoreSignal=new EventWaitHandle(false,EventResetMode.AutoReset,name+"-restore");
            if(!first){restoreSignal.Set();instance.Dispose();instance=null;Shutdown();return;}
            restoreStop=new CancellationTokenSource();var token=restoreStop.Token;
            _=Task.Run(()=>
            {
                var handles=new WaitHandle[]{restoreSignal,snapshotSignal,token.WaitHandle};
                while(!token.IsCancellationRequested)
                {
                    var wake=WaitHandle.WaitAny(handles);
                    if(wake==2)break;
                    if(wake==0)Dispatcher.BeginInvoke(()=>((MainWindow?)MainWindow)?.Restore());
                    if(wake==1)Dispatcher.BeginInvoke(async ()=>
                    {
                        if(MainWindow is MainWindow running)
                        {var json=running.DiagnosticSnapshot();await File.WriteAllTextAsync(snapshotPath,json);}
                    });
                }
            },token);
        }
        var window = new MainWindow(); MainWindow = window;
        if(e.Args.Contains("--observe-state"))
        {var receipt=e.Args.SkipWhile(a=>a!="--observe-state").Skip(1).FirstOrDefault();if(receipt is not null)window.ObserveConfiguredState(receipt);}
        if(!e.Args.Contains("--background"))window.Show();
        if(e.Args.Contains("--authorized-trial"))
        {
            var arguments=e.Args.SkipWhile(a=>a!="--authorized-trial").Skip(1).ToArray();
            if(arguments.Length!=2){Shutdown(2);return;}
            await window.BeginAuthorizedTrialAsync(arguments[0],arguments[1]);return;
        }
        if (e.Args.Contains("--setup"))
        {
            SetupReceipt = e.Args.SkipWhile(a => a != "--setup").Skip(1).FirstOrDefault();
            await window.ShowRegistrationAsync(true); return;
        }
        if (!SmokeMode) {await window.RestoreConfiguredConnectionAsync();return;}
        var smokeOutput = e.Args.SkipWhile(a => a != "--smoke-test").Skip(1).FirstOrDefault();
        if (string.IsNullOrEmpty(smokeOutput)) { Shutdown(2); return; }
        try { await window.RunSmokeAsync(smokeOutput); File.WriteAllText(Path.Combine(smokeOutput, "ui-smoke.txt"), "PASS startup, demo rendering, topmost toggle, resize, font changes, clear, pause, bridge process integration, connection/reconnect/error states, sound request deduplication.\nAudio output, physical dragging and multi-monitor DPI are NOT verified."); await window.ExitAsync(); }
        catch (Exception ex) { Directory.CreateDirectory(smokeOutput); File.WriteAllText(Path.Combine(smokeOutput, "ui-smoke.txt"), "FAIL " + ex.GetType().Name + " stage=" + SmokeStage+"\n"+ex.StackTrace); Shutdown(1); }
    }
    protected override async void OnSessionEnding(SessionEndingCancelEventArgs e)
    {base.OnSessionEnding(e);if(MainWindow is MainWindow window)await window.ExitAsync();}
    protected override void OnExit(ExitEventArgs e)
    {
        restoreStop?.Cancel();restoreSignal?.Set();
        if(instance is not null){try{instance.ReleaseMutex();}catch(ApplicationException){}instance.Dispose();}
        // Waiting worker owns signal lifetime until process exit; no disposal race.
        base.OnExit(e);
    }

}
