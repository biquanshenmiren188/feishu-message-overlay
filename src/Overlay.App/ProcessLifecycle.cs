using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Text.Json;
namespace Overlay.App;

// Rare lifecycle writes only. Never exception.Message, payloads, paths, credentials or URLs.
internal static class ProcessLifecycle
{
    [DllImport("kernel32.dll")] private static extern bool IsProcessInJob(IntPtr process,IntPtr job,out bool result);
    private static readonly object sync=new();
    private static bool enabled;
    internal static string ExitReason {get;set;}="unclassified";
    internal static string? TestPath {get;set;}
    internal static bool InJob {get{using var p=Process.GetCurrentProcess();return IsProcessInJob(p.Handle,IntPtr.Zero,out var result)&&result;}}
    internal static void Start(bool background)
    {
        if(App.SmokeMode)return;
        enabled=true;Write("start",background?"background":"visible");
        AppDomain.CurrentDomain.UnhandledException+=(_,e)=>Write("exception","app_domain",e.ExceptionObject as Exception);
        TaskScheduler.UnobservedTaskException+=(_,e)=>Write("exception","unobserved_task",e.Exception);
    }
    internal static void Write(string kind,string reason,Exception? exception=null)
    {
        if(!enabled&&TestPath is null)return;
        if(kind is not ("start" or "exit_requested" or "exit" or "exception" or "session_query"))return;
        if(reason is not ("background" or "visible" or "unclassified" or "tray_exit" or "session_ending" or "dispatcher" or "app_domain" or "unobserved_task"))return;
        try
        {
            var frames=exception is null?Array.Empty<string>():new StackTrace(exception,false).GetFrames()
                .Where(f=>f.GetMethod()?.DeclaringType?.Assembly==typeof(App).Assembly)
                .Take(4).Select(f=>f.GetMethod()!.DeclaringType!.FullName+"."+f.GetMethod()!.Name).ToArray();
            var row=JsonSerializer.Serialize(new{at=DateTimeOffset.UtcNow,pid=Environment.ProcessId,kind,reason,
                inJob=InJob,exceptionType=exception?.GetType().FullName,methods=frames})+Environment.NewLine;
            lock(sync)
            {
                var path=TestPath??Path.Combine(LocalStorage.DirectoryPath,"lifecycle.jsonl");
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                if(File.Exists(path)&&new FileInfo(path).Length+System.Text.Encoding.UTF8.GetByteCount(row)>16384)
                    File.Move(path,path+".previous",true);
                File.AppendAllText(path,row,System.Text.Encoding.UTF8);
            }
        }
        catch(Exception e)when(e is IOException or UnauthorizedAccessException or System.Security.SecurityException){}
    }
    internal static void Contract(string directory)
    {
        var path=Path.Combine(directory,"lifecycle-fixture.jsonl");TestPath=path;
        try
        {
            if(File.Exists(path))File.Delete(path);
            Write("start","visible");Write("exception","dispatcher",new InvalidOperationException("synthetic-private-body-secret-url"));
            Write("exit_requested","tray_exit");Write("exit","tray_exit");
            var text=File.ReadAllText(path);
            if(text.Contains("synthetic-private")||text.Contains("secret-url")||text.Split('\n',StringSplitOptions.RemoveEmptyEntries).Length!=4)
                throw new InvalidOperationException("Lifecycle whitelist contract");
            using(var record=JsonDocument.Parse(text.Split('\n')[1]))if(record.RootElement.GetProperty("exceptionType").GetString()!="System.InvalidOperationException")
                throw new InvalidOperationException("Lifecycle exception type contract");
            File.WriteAllText(path,new string(' ',16380));Write("start","visible");
            if(new FileInfo(path).Length>16384||new FileInfo(path+".previous").Length>16384)
                throw new InvalidOperationException("Lifecycle bounded rotation contract");
            File.Delete(path);File.Delete(path+".previous");
        }
        finally{TestPath=null;}
    }
}
