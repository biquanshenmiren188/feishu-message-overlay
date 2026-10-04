using System.Text.Json;
namespace Overlay.App;
public sealed record CardMetadata(int Buttons,int Targets,bool Header,bool Title,bool Callback,string[] Shapes,string Detail,int? Code,string[] RequiredScopes)
{
    private static readonly HashSet<string> States=new(["not_needed","disabled","busy","api_rejected","identity_mismatch","enriched","detail_has_no_targets","timeout","request_failed"],StringComparer.Ordinal);
    private static readonly HashSet<string> Fields=new(["url","href","multi_url","open_url","behaviors","action","value","default_url","pc_url"],StringComparer.Ordinal);
    private static readonly HashSet<string> Kinds=new(["null","array","object","string","number","boolean"],StringComparer.Ordinal);
    internal static CardMetadata? Project(JsonElement node)
    {
        try
        {
            var buttons=node.GetProperty("buttons").GetInt32();var targets=node.GetProperty("targets").GetInt32();
            var detail=node.GetProperty("detail").GetString()??"";
            var shapes=node.GetProperty("shapes").EnumerateArray().Select(x=>x.GetString()??"").ToArray();
            if(buttons<0||buttons>2048||targets<0||targets>buttons||!States.Contains(detail)||shapes.Length>20||shapes.Any(x=>{var parts=x.Split(':');return parts.Length!=2||!Fields.Contains(parts[0])||!Kinds.Contains(parts[1]);}))return null;
            var scopes=node.TryGetProperty("requiredScopes",out var required) && required.ValueKind==JsonValueKind.Array?required.EnumerateArray().Take(4).Select(v=>v.GetString()??"").Where(v=>v is "im:message:readonly" or "im:message" or "im:message.group_msg").Distinct().ToArray():[];
            return new(buttons,targets,node.GetProperty("header").GetBoolean(),node.GetProperty("title").GetBoolean(),node.GetProperty("callback").GetBoolean(),shapes,detail,node.TryGetProperty("code",out var code)&&code.ValueKind==JsonValueKind.Number&&code.TryGetInt32(out var number)?number:null,scopes);
        }
        catch(Exception error) when(error is JsonException or InvalidOperationException or KeyNotFoundException or FormatException){return null;}
    }
}
