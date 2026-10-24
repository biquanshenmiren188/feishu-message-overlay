using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Overlay.App;

// A desktop binding selects rules only. It never creates or moves a phone subscription.
internal sealed class DesktopPushBinding
{
    private readonly string path;
    private readonly Action<string,byte[]> write;
    internal string? Code {get;private set;}
    internal bool Readable=>Code is not null;
    internal bool Bound=>Code is {Length:8};
    internal static bool Valid(string code)=>code.Length==8&&code.All(c=>c is >= '0' and <= '9');
    internal DesktopPushBinding(string path,Action<string,byte[]>? writer=null)
    {this.path=path;write=writer??LocalStorage.AtomicWrite;Load();}
    private void Load()
    {
        byte[]? plain=null;
        try
        {
            plain=CredentialVault.TransformPublisherKey(File.ReadAllBytes(path),false);
            var value=Encoding.UTF8.GetString(plain);
            Code=value.Length==0||Valid(value)?value:null;
        }
        catch(FileNotFoundException){Code="";}
        catch(DirectoryNotFoundException){Code="";}
        catch(Exception e) when(e is IOException or UnauthorizedAccessException or CryptographicException){Code=null;}
        finally{if(plain is not null)CryptographicOperations.ZeroMemory(plain);}
    }
    internal async Task<bool> ChangeAsync(string candidate,Func<string,Task> verify)
    {
        if(candidate.Length!=0&&!Valid(candidate))throw new ArgumentException("请输入 8 位数字推送码。");
        // An explicit unbind must work while offline. It changes only this local binding.
        if(candidate.Length>0)await verify(candidate);
        var plain=Encoding.UTF8.GetBytes(candidate);
        try
        {
            var protectedBytes=CredentialVault.TransformPublisherKey(plain,true);
            write(path,protectedBytes);
            Code=candidate;
            return true;
        }
        catch(Exception e) when(e is IOException or UnauthorizedAccessException or CryptographicException){return false;}
        finally{CryptographicOperations.ZeroMemory(plain);}
    }
    internal static DesktopRuleDecisions ValidateState(JsonElement root,string code)
    {
        if(!root.TryGetProperty("pushBinding",out var binding)||binding.GetProperty("protocol").GetInt32()!=1
            ||binding.GetProperty("bound").GetBoolean()!=(code.Length>0)
            ||binding.GetProperty("canManage").GetBoolean()!=(code.Length>0))throw new JsonException("Push binding protocol mismatch");
        var rules=DesktopRuleDecisions.Parse(root.GetProperty("desktopRules"));
        if(code.Length==0 && (!rules.DesktopEnabled||!rules.CardsEnabled||root.GetProperty("desktopRules").GetProperty("messages").EnumerateObject().Any()
            ||root.GetProperty("desktopRules").GetProperty("cards").EnumerateObject().Any()))throw new JsonException("Unbound rules must allow all");
        return rules;
    }
    internal static async Task VerifyAsync(string code)
    {
        using var response=await PublicWebPublisher.SendControlAsync("/radar/api/robot-push/control",new{action="state",desktopRules=1,pushCode=code});
        if(!response.RootElement.GetProperty("cloudMode").GetBoolean())throw new JsonException();
        _=ValidateState(response.RootElement,code);
    }
}
