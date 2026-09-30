using System.Windows;
using System.IO;
namespace Overlay.App;
public partial class App : Application
{
    private Mutex? instance;
    private EventWaitHandle? restoreSignal;
    private CancellationTokenSource? restoreStop;
    public static bool SmokeMode { get; private set; }
    public static string? SetupReceipt { get; private set; }
    internal static string SmokeStage { get; set; } = "ui";
    protected override async void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        SmokeMode = e.Args.Contains("--smoke-test");
        if(e.Args.Contains("--diagnostic-contract-tests"))
        {
            SmokeMode=true;ShutdownMode=ShutdownMode.OnExplicitShutdown;
            var diagnosticOutput=e.Args.SkipWhile(a=>a!="--diagnostic-contract-tests").Skip(1).First();
            try{await ConnectionDiagnostics.ContractAsync(diagnosticOutput);Shutdown();}catch{File.WriteAllText(diagnosticOutput,"FAIL diagnostic contract");Shutdown(1);}return;
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
            instance=new Mutex(true,name,out var first);
            restoreSignal=new EventWaitHandle(false,EventResetMode.AutoReset,name+"-restore");
            if(!first){restoreSignal.Set();instance.Dispose();instance=null;Shutdown();return;}
            restoreStop=new CancellationTokenSource();var token=restoreStop.Token;
            _=Task.Run(()=>{while(!token.IsCancellationRequested){if(restoreSignal.WaitOne(500))Dispatcher.BeginInvoke(()=>((MainWindow?)MainWindow)?.Restore());}},token);
        }
        var window = new MainWindow(); MainWindow = window;
        if(!e.Args.Contains("--background"))window.Show();
        if (e.Args.Contains("--setup"))
        {
            SetupReceipt = e.Args.SkipWhile(a => a != "--setup").Skip(1).FirstOrDefault();
            await window.ShowRegistrationAsync(true); return;
        }
        if (!SmokeMode) return;
        var output = e.Args.SkipWhile(a => a != "--smoke-test").Skip(1).FirstOrDefault();
        if (string.IsNullOrEmpty(output)) { Shutdown(2); return; }
        try { await window.RunSmokeAsync(output); File.WriteAllText(Path.Combine(output, "ui-smoke.txt"), "PASS startup, demo rendering, topmost toggle, resize, font changes, clear, pause, bridge process integration, connection/reconnect/error states, sound request deduplication.\nAudio output, physical dragging and multi-monitor DPI are NOT verified."); await window.ExitAsync(); }
        catch (Exception ex) { Directory.CreateDirectory(output); File.WriteAllText(Path.Combine(output, "ui-smoke.txt"), "FAIL " + ex.GetType().Name + " stage=" + SmokeStage); Shutdown(1); }
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
