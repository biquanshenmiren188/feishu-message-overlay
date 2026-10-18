using System.Text.Json;
using Overlay.Core;
internal static class CompactSummaryTests
{
    public static void Run(Action<bool,string> check)
    {
        using var document=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"summary-fixtures.json")));
        foreach(var fixture in document.RootElement.EnumerateArray())
        {
            var input=fixture.GetProperty("input");var expected=fixture.GetProperty("expected");
            var actual=CompactMessage.From(input.TryGetProperty("title",out var title)?title.GetString():null,input.GetProperty("body").GetString());
            foreach(var (key,value) in new[]{("title",actual.Title),("signals",actual.Signals),("spread",actual.Spread),("risk",actual.Risk)})
                check(value==expected.GetProperty(key).GetString(),"web/desktop summary parity "+fixture.GetProperty("name").GetString()+" / "+key);
            check(actual.Warning==expected.GetProperty("warning").GetBoolean(),"web/desktop warning parity");
        }
    }
}
