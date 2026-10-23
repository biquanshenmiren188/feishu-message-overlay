using System.Text.Json;
namespace Overlay.App;

// The signed reader supplies decisions, never a browser's local draft.
internal sealed class DesktopRuleDecisions
{
    internal static readonly DesktopRuleDecisions Empty=new();
    internal string Signature {get;private init;}="";
    internal long Revision {get;private init;}
    internal bool DesktopEnabled {get;private init;}=true;
    internal bool CardsEnabled {get;private init;}=true;
    private readonly Dictionary<string,string> messages=new(StringComparer.Ordinal),cards=new(StringComparer.Ordinal);
    internal bool ShowMessage(string id)=>DesktopEnabled&&messages.GetValueOrDefault(id)!="hide";
    internal bool SoundMessage(string id)=>DesktopEnabled&&!messages.ContainsKey(id);
    internal IReadOnlySet<string> MutedMessageIds()=>messages.Where(pair=>DesktopEnabled&&pair.Value=="mute").Select(pair=>pair.Key).ToHashSet(StringComparer.Ordinal);
    internal bool ShowCard(string id)=>CardsEnabled&&!cards.ContainsKey(id);
    internal static DesktopRuleDecisions Parse(JsonElement value)
    {
        var result=new DesktopRuleDecisions{Signature=value.GetRawText(),Revision=value.GetProperty("revision").GetInt64(),DesktopEnabled=value.GetProperty("desktopEnabled").GetBoolean(),CardsEnabled=value.GetProperty("cardsEnabled").GetBoolean()};
        foreach(var (name,target) in new[]{("messages",result.messages),("cards",result.cards)})
            foreach(var item in value.GetProperty(name).EnumerateObject().Take(1101))
            {var action=item.Value.GetString();if(item.Name.Length>512||action is not ("hide" or "mute")||target.Count>=1100)throw new JsonException();target[item.Name]=action;}
        return result;
    }
}
