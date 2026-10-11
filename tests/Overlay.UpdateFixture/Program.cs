using System.Text.Json;

// Isolated updater process fixture: no UI, network, credentials or real app state.
var mode=File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"fixture-mode.txt"));
var receipt=args.SkipWhile(a=>a!="--update-health-receipt").Skip(1).FirstOrDefault();
if(mode=="crash")return 1;
File.WriteAllText(Path.Combine(AppContext.BaseDirectory,"launched.json"),JsonSerializer.Serialize(new{pid=Environment.ProcessId,mode}));
if(receipt is not null)
{
    var temp=receipt+".tmp";
    File.WriteAllText(temp,mode=="bad-receipt"?"invalid JSON":JsonSerializer.Serialize(new{pid=Environment.ProcessId,version="v2026.10.12.1"}));
    File.Move(temp,receipt,true);
}
await Task.Delay(TimeSpan.FromMinutes(2));
return 0;
