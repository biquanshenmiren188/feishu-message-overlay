using System.IO;
using System.Text.RegularExpressions;
namespace Overlay.App;
public sealed class ConnectionSettings
{
    public string AppId { get; init; } = "";
    public string Secret { get; set; } = "";
    public string[] ChatIds { get; init; } = [];
    public string[] BotIds { get; init; } = [];
    public static string[] Split(string text) => text.Split(['\r', '\n', ',', ';', ' ', '\t'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).Distinct(StringComparer.Ordinal).ToArray();
    public static string? Validate(string appId, string secret, string[] chats, string[] bots)
    {
        if (!Regex.IsMatch(appId, "^cli_[a-zA-Z0-9]+$")) return "App ID 格式不正确，应以 cli_ 开头";
        if (string.IsNullOrWhiteSpace(secret) || secret.Length > 4096) return "请在本机输入此应用的 App Secret";
        if (chats.Length is < 1 or > 5 || chats.Any(id => !Regex.IsMatch(id, "^oc_[a-zA-Z0-9_-]+$"))) return "请输入一至五个核验过的 oc_ 群 ID，每行一个；不要输入群名称";
        if (bots.Length > 50 || bots.Any(id => !Regex.IsMatch(id, "^ou_[a-zA-Z0-9_-]+$"))) return "机器人筛选使用准确 ou_ 发送者 ID，或留空接收选定群中所有机器人";
        return null;
    }
    public static string FindNode()
    {
        var local = Path.Combine(AppContext.BaseDirectory, "runtime", "node.exe"); if (File.Exists(local)) return local;
        foreach (var directory in (Environment.GetEnvironmentVariable("PATH") ?? "").Split(Path.PathSeparator))
        {
            try { var path = Path.Combine(directory, "node.exe"); if (File.Exists(path)) return path; } catch (ArgumentException) { }
        }
        var installed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "nodejs", "node.exe");
        if (File.Exists(installed)) return installed;
        throw new FileNotFoundException("需要 Node.js 22 或兼容运行时");
    }
}
