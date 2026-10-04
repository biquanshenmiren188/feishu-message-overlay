using System.Diagnostics;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
namespace Overlay.App;
internal static class GroupDiscovery
{
    internal sealed record Match(string State,string Target,string? ChatId,int Code,int Count,bool Complete);
    internal static bool TryProject(string line,string target,out Match? match)
    {
        match=null;
        try{
            using var doc=JsonDocument.Parse(line.TrimStart('\uFEFF',' ','\t'));var root=doc.RootElement;
            if(root.ValueKind!=JsonValueKind.Object||root.GetProperty("kind").GetString()!="group_match"||root.GetProperty("target").GetString()!=target)return false;
            var code=root.GetProperty("code").GetInt32();var count=root.GetProperty("count").GetInt32();var complete=root.GetProperty("complete").GetBoolean();
            var chat=root.GetProperty("chatId").ValueKind==JsonValueKind.String?root.GetProperty("chatId").GetString():null;
            if(count<0||count>2000||chat is not null&&!Regex.IsMatch(chat,"^oc_[a-zA-Z0-9_-]+$"))return false;
            var state=code!=0?"api_error":!complete?"incomplete":count==0?"not_joined":count!=1?"ambiguous":chat is null?"invalid_response":"matched";
            match=new(state,target,state=="matched"?chat:null,code,count,complete);return true;
        }catch(Exception error)when(error is JsonException or InvalidOperationException or KeyNotFoundException or FormatException){return false;}
    }
    internal static async Task<Match> FindAsync(ConnectionSettings settings,string target)
    {
        using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(45));Process? child=null;
        try{
            var script=Path.Combine(AppContext.BaseDirectory,"bridge","group-discover.mjs");
            var start=new ProcessStartInfo(ConnectionSettings.FindNode()){UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=Path.GetDirectoryName(script)!,StandardInputEncoding=new UTF8Encoding(false),StandardOutputEncoding=new UTF8Encoding(false)};
            start.ArgumentList.Add(script);child=Process.Start(start)??throw new InvalidOperationException();var process=child;
            var discard=Task.Run(async()=>{var buffer=new char[4096];try{while(await process.StandardError.ReadAsync(buffer,timeout.Token)>0)Array.Clear(buffer);}catch(OperationCanceledException){}catch(IOException){}finally{Array.Clear(buffer);}});
            await child.StandardInput.WriteLineAsync(JsonSerializer.Serialize(new{appId=settings.AppId,appSecret=settings.Secret,target}).AsMemory(),timeout.Token);await child.StandardInput.FlushAsync(timeout.Token);settings.Secret="";
            var total=0;
            for(var count=0;count<64;count++){
                var line=await child.StandardOutput.ReadLineAsync(timeout.Token);if(line is null)break;total+=line.Length;
                if(line.Length>32768||total>131072)break;
                if(TryProject(line,target,out var match)){await child.WaitForExitAsync(timeout.Token);await discard;return match!;}
            }
            return new("response_missing",target,null,-1,0,false);
        }catch(OperationCanceledException){return new("timeout",target,null,-1,0,false);}
        catch(Exception){return new("local_error",target,null,-1,0,false);}
        finally{settings.Secret="";if(child is not null){try{if(!child.HasExited)child.Kill(entireProcessTree:true);}catch(InvalidOperationException){}child.Dispose();}}
    }
}
