using System.IO;
using System.Windows;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunYieldContractAsync(string output,bool inputOnly=false,bool dragOnly=false)
    {
        Directory.CreateDirectory(output);
        void Assert(bool condition,[System.Runtime.CompilerServices.CallerArgumentExpression(nameof(condition))] string? expression=null){if(!condition)throw new InvalidOperationException(expression);}
        Pin.IsChecked=true;PreferenceChanged(this,new());
        if(!inputOnly){
        App.SmokeStage="drag_yield";
        Assert(dragYield is {IsHooked:true,NativeTopmost:true});
        var yieldEvidence=new List<object>();
        foreach(var action in new[]{"move","size","cancel","manualOff"})
        {
            Pin.IsChecked=true;PreferenceChanged(this,new());
            var stages=new List<string>();nint foreground=0;var stableFocus=true;var topOff=false;var topRestored=false;
            var geometry=System.Text.Json.JsonSerializer.Serialize(WindowPlacement.Snapshot(this));
            void Observed(string stage)
            {
                stages.Add(stage);
                if(stage=="yielded")
                {
                    foreground=DragYield.GetForegroundWindow();topOff=!dragYield!.NativeTopmost;
                    if(action=="manualOff"){Pin.IsChecked=false;PreferenceChanged(this,new());}
                }
                else {stableFocus&=dragYield!.RestoreKeptForeground;topRestored=dragYield.NativeTopmost;}
            }
            dragYield!.Changed+=Observed;
            var fixture=System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!,"--drag-yield-fixture "+(action=="manualOff"?"move":action)){UseShellExecute=false,CreateNoWindow=true})!;
            await fixture.WaitForExitAsync();await Task.Delay(2000);
            Assert(!dragYield.NativeTopmost); // Fixture exits 800ms after ending the move; still below five seconds.
            await Task.Delay(3500);dragYield.Changed-=Observed;
            File.WriteAllText(Path.Combine(output,"drag-yield-last.json"),System.Text.Json.JsonSerializer.Serialize(new{action,stages,topOff,topRestored,stableFocus,currentTopmost=dragYield.NativeTopmost}));
            Assert(fixture.ExitCode==0 && stages.Contains("yielded") && topOff);
            Assert(action=="manualOff"?!dragYield.NativeTopmost:stages.Contains("restored") && topRestored && stableFocus);
            Assert(geometry==System.Text.Json.JsonSerializer.Serialize(WindowPlacement.Snapshot(this)));
            yieldEvidence.Add(new{action,stages,topOff,topRestored,stableFocus,geometryUnchanged=true});fixture.Dispose();
        }
        Pin.IsChecked=true;PreferenceChanged(this,new());
        File.WriteAllText(Path.Combine(output,"drag-yield-runtime.json"),System.Text.Json.JsonSerializer.Serialize(yieldEvidence));
        var ownEvents=0;void OwnEvent(string stage){ownEvents++;}
        dragYield!.Changed+=OwnEvent;await DragYieldFixture.RunAsync("move");dragYield.Changed-=OwnEvent;
        Assert(ownEvents==0 && dragYield.NativeTopmost);
        File.WriteAllText(Path.Combine(output,"drag-yield-own-window.txt"),"PASS same-process synthetic window move emits no yield; own and settings windows share this exclusion.");
        }
        if(dragOnly){await File.WriteAllTextAsync(Path.Combine(output,"yield-contract.txt"),"PASS drag/resize/cancel, five-second delay, manual pin off, own-window exclusion and foreground retention.");return;}
        App.SmokeStage="browser_input_yield";
        var token="Local\\OverlaySynthetic-"+Guid.NewGuid().ToString("N");
        using(var inputReady=new EventWaitHandle(false,EventResetMode.AutoReset,token+"-ready"))
        using(var inputNext=new EventWaitHandle(false,EventResetMode.AutoReset,token+"-next"))
        using(var inputDone=new EventWaitHandle(false,EventResetMode.AutoReset,token+"-done"))
        {
            var test=System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo(Environment.ProcessPath!,"--browser-input-fixture "+token){UseShellExecute=false,CreateNoWindow=true})!;
            DragYield.SyntheticBrowserProcessId=test.Id;
            try
            {
                Assert(await Task.Run(()=>inputReady.WaitOne(5000)));dragYield!.OwnInput();await Task.Delay(600);
                Assert(dragYield.BrowserWatchActive && dragYield.NativeTopmost && dragYield.ClickWatchActive);
                var inputEvidence=new List<object>();
                for(var input=0;input<3;input++)
                {
                    inputNext.Set();Assert(await Task.Run(()=>inputDone.WaitOne(3000)));await Task.Delay(600);
                    File.WriteAllText(Path.Combine(output,"click-state.json"),System.Text.Json.JsonSerializer.Serialize(new{phase="noClick",input,dragYield.ObservedClicks,dragYield.ExternalClicks,dragYield.Yielding,dragYield.NativeTopmost,dragYield.BrowserWatchActive}));
                    Assert(!dragYield.Yielding && dragYield.NativeTopmost);
                    inputEvidence.Add(new{input,phase="moveWheelKeyDoNotInitiate",at=DateTimeOffset.UtcNow,yielding=dragYield.Yielding});
                }
                for(var input=0;input<3;input++)
                {
                    inputNext.Set();Assert(await Task.Run(()=>inputDone.WaitOne(3000)));await Task.Delay(600);
                    File.WriteAllText(Path.Combine(output,"click-state.json"),System.Text.Json.JsonSerializer.Serialize(new{phase="clicked",input,dragYield.ObservedClicks,dragYield.ExternalClicks,dragYield.Yielding,dragYield.NativeTopmost,dragYield.BrowserWatchActive}));
                    Assert(dragYield.Yielding && !dragYield.NativeTopmost && dragYield.BrowserWatchActive);
                    inputEvidence.Add(new{input,at=DateTimeOffset.UtcNow,yielding=dragYield.Yielding,topmost=dragYield.NativeTopmost});
                }
                // The fixture acknowledges 50ms after SendInput; 600ms sampling already elapsed.
                await Task.Delay(4150);Assert(dragYield.Yielding && !dragYield.NativeTopmost);
                inputEvidence.Add(new{input=3,phase="underFiveSeconds",at=DateTimeOffset.UtcNow,yielding=dragYield.Yielding});
                await Task.Delay(800);Assert(!dragYield.Yielding && dragYield.NativeTopmost && dragYield.RestoreKeptForeground);
                inputEvidence.Add(new{input=4,phase="idleRestored",at=DateTimeOffset.UtcNow,yielding=dragYield.Yielding});
                inputNext.Set();Assert(await Task.Run(()=>inputDone.WaitOne(3000)));await Task.Delay(600);
                Assert(!dragYield.Yielding && dragYield.NativeTopmost);
                inputEvidence.Add(new{input=6,phase="moveAfterRestoreStaysTopmost",at=DateTimeOffset.UtcNow,yielding=dragYield.Yielding});
                inputNext.Set();Assert(await Task.Run(()=>inputDone.WaitOne(3000)));await Task.Delay(600);
                Assert(dragYield.Yielding && !dragYield.NativeTopmost);
                Pin.IsChecked=false;PreferenceChanged(this,new());await Task.Delay(5500);
                Assert(!dragYield.NativeTopmost && !dragYield.BrowserWatchActive && !dragYield.ClickWatchActive);
                Pin.IsChecked=true;PreferenceChanged(this,new());BrowserInputFixture.ClickSyntheticWindow(this,test.Id);await Task.Delay(600);
                Assert(!dragYield.Yielding && !dragYield.BrowserWatchActive && dragYield.NativeTopmost);
                Hide();Assert(!dragYield.BrowserWatchActive && !dragYield.ClickWatchActive);Show();
                File.WriteAllText(Path.Combine(output,"browser-yield-runtime.json"),System.Text.Json.JsonSerializer.Serialize(new{inputEvidence,alreadyForegroundClick=true,wheelAndKeyExtend=true,manualOffCancels=true,ownWindowExcluded=true,hiddenStopsWatch=true,fixture="synthetic ordinary native window exercising the shared external-window input policy; no private window contents accessed"}));
            }
            finally {inputNext.Set();await test.WaitForExitAsync();DragYield.SyntheticBrowserProcessId=0;test.Dispose();}
        }
        await File.WriteAllTextAsync(Path.Combine(output,"yield-contract.txt"),"PASS click-only external yield; move/wheel/key cannot initiate yield; movement after restoration stays topmost; input extends five-second idle; manual pin off, hook cleanup, own window exclusion and foreground retention."+(inputOnly?"":" Drag/resize/cancel also passed."));
    }
}
