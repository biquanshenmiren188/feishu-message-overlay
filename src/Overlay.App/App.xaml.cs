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
        if(e.Args.Length==2&&e.Args[0]=="--verify-update-source")
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;base.OnStartup(e);
            try{await GitHubUpdateTransport.VerifySourceAsync(e.Args[1]);Shutdown();}
            catch(Exception error){Directory.CreateDirectory(e.Args[1]);File.WriteAllText(Path.Combine(e.Args[1],"update-source-check.json"),System.Text.Json.JsonSerializer.Serialize(new{passed=false,type=error.GetType().Name}));Shutdown(1);}return;
        }
        if(e.Args.Length==2&&e.Args[0]=="--apply-desktop-update")
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;base.OnStartup(e);
            Shutdown(await DesktopAutoUpdate.RunInstallerAsync(e.Args[1]));return;
        }
        if(e.Args.Contains("--weixin-contract")){
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            try{await WeixinContract.RunAsync(e.Args.Last());Shutdown();}catch{Shutdown(1);}return;
        }
        base.OnStartup(e);
        if(e.Args.Length==2&&e.Args[0]=="--compact-summary-contract")
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            try{await CompactSummaryContract.RunAsync(e.Args[1]);Shutdown();}
            catch(Exception error){Directory.CreateDirectory(e.Args[1]);File.WriteAllText(Path.Combine(e.Args[1],"desktop-summary-contract.json"),System.Text.Json.JsonSerializer.Serialize(new{passed=false,error=error.ToString()}));Shutdown(1);}return;
        }
        if(e.Args.Contains("--yield-contract"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            Preferences.ContractPath=Path.Combine(Path.GetTempPath(),"yield-ui-"+Guid.NewGuid().ToString("N")+".json");
            var output=e.Args.Last();Directory.CreateDirectory(output);
            var fixture=new MainWindow();MainWindow=fixture;fixture.Show();
            try{await fixture.RunYieldContractAsync(output,e.Args.Contains("--input-only"),e.Args.Contains("--drag-only"));await fixture.ExitAsync();}
            catch(Exception error){await File.WriteAllTextAsync(Path.Combine(output,"yield-contract.txt"),"FAIL "+error);Shutdown(1);}return;
        }
        if(e.Args.Contains("--opportunity-contract")||e.Args.Contains("--card-column-height-contract"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            Preferences.ContractPath=Path.Combine(Path.GetTempPath(),"opportunity-ui-"+Guid.NewGuid().ToString("N")+".json");
            var fixture=new MainWindow{ShowActivated=false};MainWindow=fixture;fixture.Loaded+=(_,_)=>{fixture.Left=-12000;fixture.Top=-12000;};fixture.Show();
            try{if(e.Args.Contains("--card-column-height-contract"))await fixture.RunCardColumnHeightContractAsync(e.Args.Last());else await fixture.RunOpportunityContractAsync(e.Args.Last());await fixture.ExitAsync();}
            catch(Exception error){await File.WriteAllTextAsync(e.Args.Last(),System.Text.Json.JsonSerializer.Serialize(new{passed=false,error=error.ToString()}));await fixture.ExitAsync();Shutdown(1);}return;
        }
        SmokeMode = e.Args.Contains("--smoke-test") || e.Args.Contains("--measure-current-window");
        if(e.Args.Contains("--cloud-window-contract"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            Preferences.ContractPath=Path.Combine(Path.GetTempPath(),"cloud-ui-fixture-"+Guid.NewGuid().ToString("N")+".json");
            var fixture=new MainWindow{ShowActivated=false};MainWindow=fixture;
            fixture.Loaded+=(_,_)=>{fixture.Left=-12000;fixture.Top=-12000;};fixture.Show();
            try{await fixture.RunCloudWindowContractAsync(e.Args.Last());await fixture.ExitAsync();}
            catch{await File.WriteAllTextAsync(e.Args.Last(),"{\"passed\":false,\"error\":\"cloud_wpf_contract\"}");await fixture.ExitAsync();Shutdown(1);}
            return;
        }
        if(e.Args.Contains("--cloud-source-contract"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            try{await CloudSourceContract.RunAsync(e.Args.Last());Shutdown();}catch{Shutdown(1);}return;
        }
        if(e.Args.Contains("--cloud-source-mode"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--cloud-source-mode").Skip(1).ToArray();
            if(args.Length!=1 || args[0] is not ("on" or "off")){Shutdown(2);return;}
            CloudMode.Set(args[0]=="on");Shutdown();return;
        }
        if(e.Args.Contains("--cloud-setup-check"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;var reachable=false;int? status=null;
            try{using var result=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/configure",new{});}
            catch(System.Net.Http.HttpRequestException error){status=(int?)error.StatusCode;reachable=status==400;}
            catch{ }
            await File.WriteAllTextAsync(e.Args.Last(),System.Text.Json.JsonSerializer.Serialize(new{signedEndpointVerified=reachable,httpStatus=status,credentialSubmitted=false}));
            Shutdown(reachable?0:1);return;
        }
        if(e.Args.Contains("--cloud-setup"))
        {
            ShutdownMode=ShutdownMode.OnLastWindowClose;
            var receipt=e.Args.SkipWhile(a=>a!="--cloud-setup").Skip(1).FirstOrDefault();
            MainWindow=new CloudSetupWindow(receipt);MainWindow.Show();return;
        }
        if(e.Args.Contains("--configure-web-publisher"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;var args=e.Args.SkipWhile(a=>a!="--configure-web-publisher").Skip(1).ToArray();if(args.Length!=2){Shutdown(2);return;}
            try{var result=PublicWebPublisher.Configure(args[0]);await File.WriteAllTextAsync(args[1],System.Text.Json.JsonSerializer.Serialize(result));Shutdown();}catch{await File.WriteAllTextAsync(args[1],"{\"configured\":false,\"error\":\"setup_failed\"}");Shutdown(1);}return;
        }
        if(e.Args.Contains("--web-publisher-contract"))
        {ShutdownMode=ShutdownMode.OnExplicitShutdown;try{PublicWebPublisher.WriteContractVectors(e.Args.Last());Shutdown();}catch{Shutdown(1);}return;}
        if(e.Args.Contains("--add-authorized-group"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var args=e.Args.SkipWhile(a=>a!="--add-authorized-group").Skip(1).ToArray();if(args.Length!=2){Shutdown(2);return;}
            var existing=ConnectionSelection.Load();var credentials=CredentialVault.LoadOnUserRequest();
            if(existing is null || credentials is null || existing.AppId!=credentials.AppId){if(credentials is not null)credentials.Secret="";Shutdown(1);return;}
            var match=await GroupDiscovery.FindAsync(credentials,args[0]);var ids=match.State=="matched"?existing.ChatIds.Append(match.ChatId!).Distinct(StringComparer.Ordinal).ToArray():existing.ChatIds;
            var saved=match.State=="matched" && ids.Length<=5 && ConnectionSelection.Save(new ConnectionSettings{AppId=credentials.AppId,Secret="validation-only",ChatIds=ids,BotIds=existing.BotIds});credentials.Secret="";
            await File.WriteAllTextAsync(args[1],System.Text.Json.JsonSerializer.Serialize(new{saved,count=ids.Length,state=match.State,chatId=match.ChatId}));Shutdown(saved?0:1);return;
        }
        if(e.Args.Contains("--enable-auto-joined"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;var prefs=Preferences.Load();var saved=(prefs with{AutoListenJoined=true}).Save();
            await File.WriteAllTextAsync(e.Args.Last(),System.Text.Json.JsonSerializer.Serialize(new{saved,enabled=saved}));Shutdown(saved?0:1);return;
        }
        if(e.Args.Contains("--check-local-state"))
        {
            ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var output=e.Args.Last();var prefs=Preferences.Load();var selected=ConnectionSelection.Load();var saved=CredentialVault.LoadOnUserRequest();
            var result=new{user=Environment.UserName,sid=System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value,appData=Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),preferencePath=Preferences.StoragePath,preferenceState=Preferences.LoadState,dwell=prefs.DwellSeconds,sound=prefs.Sound,audioExists=File.Exists(prefs.AudioPath),audioConfigured=prefs.AudioPath.Length>0,selectionLoaded=selected is not null,vaultDecrypted=saved is not null,identityMatches=saved is not null && saved.AppId==selected?.AppId};
            if(saved is not null)saved.Secret="";await File.WriteAllTextAsync(output,System.Text.Json.JsonSerializer.Serialize(result));Shutdown();return;
        }
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
            using var audio=new AlertAudio();audio.PathName="";
            var bundledDefault=audio.PathName==AlertAudio.BundledPath && AlertAudio.IsSupported(audio.PathName);
            audio.PathName=args[0];var customSelected=audio.PathName==Path.GetFullPath(args[0]);
            audio.PathName=Path.Combine(Path.GetTempPath(),Guid.NewGuid().ToString("N")+".wav");
            var missingCustomFallsBack=audio.PathName==AlertAudio.BundledPath;
            var accepted=AlertAudio.PlayWave(args[0]);
            File.WriteAllText(args[1],System.Text.Json.JsonSerializer.Serialize(new{accepted,outputDevice=AlertAudio.HasOutputDevice,bundledDefault,customSelected,missingCustomFallsBack}));
            await Task.Delay(900);Shutdown(accepted && bundledDefault && customSelected && missingCustomFallsBack?0:1);return;
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
            ProcessLifecycle.Start(e.Args.Contains("--background"));
            DispatcherUnhandledException+=(_,error)=>ProcessLifecycle.Write("exception","dispatcher",error.Exception);
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
        if(!SmokeMode)
        {
            for(var attempt=0;attempt<6;attempt++)
            {
                _=Preferences.Load();
                if(Preferences.LoadState=="loaded" || Preferences.LoadState=="missing" && !StartupRegistration.IsEnabled())break;
                await Task.Delay(500);
            }
        }
        var window = new MainWindow(); MainWindow = window;
        if(e.Args.Contains("--measure-current-window"))
        {
            var args=e.Args.SkipWhile(a=>a!="--measure-current-window").Skip(1).ToArray();
            if(args.Length!=2 || !int.TryParse(args[0],out var pid)){Shutdown(2);return;}
            window.PrepareFitProbe();window.Show();
            try{await window.MeasureCurrentWindowAsync(pid,args[1]);await window.ExitAsync();}
            catch{await File.WriteAllTextAsync(args[1],"{\"state\":\"probe_failed\",\"privateContentSaved\":false}");Shutdown(1);}
            return;
        }
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
        if (!SmokeMode) {
            if(e.Args.Contains("--update-health-receipt")){
                var receipt=e.Args.SkipWhile(a=>a!="--update-health-receipt").Skip(1).FirstOrDefault();
                if(receipt is not null&&Preferences.LoadState is "loaded" or "missing")DesktopAutoUpdate.WriteHealthReceipt(receipt);
            }
            window.StartDesktopUpdates();
            await window.RestoreConfiguredConnectionAsync();return;
        }
        var smokeOutput = e.Args.SkipWhile(a => a != "--smoke-test").Skip(1).FirstOrDefault();
        if (string.IsNullOrEmpty(smokeOutput)) { Shutdown(2); return; }
        try { await window.RunCurrentContractAsync(smokeOutput); File.WriteAllText(Path.Combine(smokeOutput, "ui-smoke.txt"), "PASS isolated persistence safety, synchronous exit flush, strict three-container reading range and real timer visual progression.\nAudio output, physical dragging and multi-monitor DPI are NOT verified."); await window.ExitAsync(); }
        catch (Exception ex) { Directory.CreateDirectory(smokeOutput); File.WriteAllText(Path.Combine(smokeOutput, "ui-smoke.txt"), "FAIL " + ex.GetType().Name + " stage=" + SmokeStage+"\n"+ex.Message+"\n"+ex.StackTrace); Shutdown(1); }
    }
    protected override void OnSessionEnding(SessionEndingCancelEventArgs e)
    {
        ProcessLifecycle.Write("session_query","session_ending");
        if(MainWindow is MainWindow window && !window.FlushForSessionEnding()){e.Cancel=true;window.Restore();}
        else if(MainWindow is MainWindow closing){ProcessLifecycle.ExitReason="session_ending";_=closing.ExitAsync();}
        base.OnSessionEnding(e);
    }
    protected override void OnExit(ExitEventArgs e)
    {
        ProcessLifecycle.Write("exit",ProcessLifecycle.ExitReason);
        restoreStop?.Cancel();restoreSignal?.Set();
        if(instance is not null){try{instance.ReleaseMutex();}catch(ApplicationException){}instance.Dispose();}
        // Waiting worker owns signal lifetime until process exit; no disposal race.
        base.OnExit(e);
    }

}
