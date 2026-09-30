using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
namespace Overlay.App;
internal static class ConnectionDiagnostics
{
    internal sealed record SafeResult(string State,string AppId,string? BotName=null,int? ActivateStatus=null,int? Code=null,int? ExitCode=null,int Lines=0,int Ignored=0);
    public static async Task RunAsync(string output,string unusedTargetFile)
    {
        var settings=CredentialVault.LoadOnUserRequest();
        if(settings is null){await File.WriteAllTextAsync(output,"{\"state\":\"no_user_approved_encrypted_configuration\"}");return;}
        var result=await QueryAsync(settings,Path.Combine(AppContext.BaseDirectory,"bridge","discover.mjs"),"bot-only",TimeSpan.FromSeconds(35));
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(result));
    }
    internal static async Task<SafeResult> QueryAsync(ConnectionSettings settings,string script,string mode,TimeSpan limit)
    {
        Process? child=null;var lines=0;var ignored=0;var state="process_start_failed";
        using var timeout=new CancellationTokenSource(limit);
        try
        {
            var info=new ProcessStartInfo(ConnectionSettings.FindNode()){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=Path.GetDirectoryName(script)!,StandardInputEncoding=new UTF8Encoding(false),StandardOutputEncoding=new UTF8Encoding(false)};
            info.ArgumentList.Add(script);child=Process.Start(info)??throw new InvalidOperationException();
            var process=child;
            var errors=Task.Run(async()=>{var buffer=new char[4096];try{while(await process.StandardError.ReadAsync(buffer,timeout.Token)>0)Array.Clear(buffer);}catch(OperationCanceledException){}catch(IOException){}finally{Array.Clear(buffer);}});
            state="private_input_failed";
            await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new{appId=settings.AppId,appSecret=settings.Secret,mode}).AsMemory(),timeout.Token);
            await child.StandardInput.FlushAsync(timeout.Token);settings.Secret="";
            state="response_missing";SafeResult? safe=null;var characters=0;
            while(lines<128)
            {
                var line=await child.StandardOutput.ReadLineAsync(timeout.Token);if(line is null)break;
                lines++;characters+=line.Length;
                if(line.Length>32768||characters>262144){state="response_limit";break;}
                line=line.TrimStart('\uFEFF',' ','\t');
                if(TryProject(line,settings.AppId,out safe))break;
                ignored++; // No raw output is ever saved, printed or returned.
            }
            if(safe is not null)
            {
                await child.WaitForExitAsync(timeout.Token);await errors;
                return safe with {ExitCode=child.ExitCode,Lines=lines,Ignored=ignored};
            }
            if(child.HasExited)return new(state,settings.AppId,ExitCode:child.ExitCode,Lines:lines,Ignored:ignored);
            return new(state,settings.AppId,Lines:lines,Ignored:ignored);
        }
        catch(OperationCanceledException){return new("timeout",settings.AppId,Lines:lines,Ignored:ignored);}
        catch(Exception){return new(state,settings.AppId,Lines:lines,Ignored:ignored);}
        finally{settings.Secret="";if(child is not null){try{if(!child.HasExited)child.Kill(entireProcessTree:true);}catch(InvalidOperationException){}child.Dispose();}}
    }
    internal static bool TryProject(string line,string expectedId,out SafeResult? safe)
    {
        safe=null;
        try
        {
            using var document=JsonDocument.Parse(line);var root=document.RootElement;
            if(root.ValueKind!=JsonValueKind.Object || !root.TryGetProperty("kind",out var kind)||kind.ValueKind!=JsonValueKind.String||kind.GetString()!="bot_info")return false;
            if(!root.TryGetProperty("appId",out var id)||id.ValueKind!=JsonValueKind.String||id.GetString()!=expectedId)return false;
            if(!root.TryGetProperty("code",out var code)||!code.TryGetInt32(out var number))return false;
            string? name=null;int? status=null;
            if(root.TryGetProperty("botName",out var title)&&title.ValueKind==JsonValueKind.String){name=title.GetString();if(name?.Length>256)return false;}
            if(root.TryGetProperty("activateStatus",out var active)&&active.TryGetInt32(out var value)&&value is >=0 and <=3)status=value;
            safe=new(number==0?"success":"api_error",expectedId,name,status,number);return true;
        }
        catch(JsonException){return false;}catch(InvalidOperationException){return false;}
    }
    internal static async Task ContractAsync(string output)
    {
        var checks=0;
        void Check(bool passed){if(!passed)throw new InvalidOperationException();checks++;}
        // Reproduce the old kind.GetString() exception without credentials.
        using(var bad=JsonDocument.Parse("{\"kind\":17}")){var reproduced=false;try{_ = bad.RootElement.GetProperty("kind").GetString();}catch(InvalidOperationException){reproduced=true;}Check(reproduced);}
        Check(!TryProject("{\"kind\":17}","cli_synthetic",out _));
        Check(!TryProject("{\"kind\":\"bot_info\",\"appId\":\"wrong\",\"code\":0}","cli_synthetic",out _));
        Check(!TryProject("{\"kind\":\"bot_info\",\"appId\":\"cli_synthetic\",\"code\":{}}","cli_synthetic",out _));
        var script=Path.Combine(AppContext.BaseDirectory,"bridge","diagnostic-fixture.mjs");
        foreach(var mode in new[]{"valid","chatter","split","crash","invalid","oversized","stall"})
        {
            var settings=new ConnectionSettings{AppId="cli_synthetic",Secret="synthetic-only"};
            var result=await QueryAsync(settings,script,mode,mode=="stall"?TimeSpan.FromSeconds(.4):TimeSpan.FromSeconds(8));
            Check(settings.Secret=="");
            Check(mode is "valid" or "chatter" or "split"?result.State=="success" && result.BotName=="测试机器人" && result.ActivateStatus==2:result.State!="success");
            Check(!JsonSerializer.Serialize(result).Contains("synthetic-only",StringComparison.Ordinal));
        }
        await File.WriteAllTextAsync(output,$"PASS {checks} diagnostic contracts: old exception reproduction, typed whitelist, UTF8/BOM, split writes, chatter, wrong identity/type, crash, invalid JSON, limits, timeout and secret-field exclusion. No credentials or network.");
    }
}
