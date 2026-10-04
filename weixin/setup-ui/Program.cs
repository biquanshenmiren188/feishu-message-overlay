using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Shapes;
class Program {
 [STAThread] static void Main(string[] args) {
  if(args.Length==3&&args[0]=="--gateway-host"){
   var sid=System.Security.Principal.WindowsIdentity.GetCurrent().User!.Value;
   using var single=new System.Threading.Mutex(true,"Local\\FeishuWeixinGateway-"+sid,out var first);if(!first)return;
   var folder=args[1];var info=new ProcessStartInfo(System.IO.Path.Combine(folder,"node-v22.22.3-win-x64","node.exe")){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,WorkingDirectory=folder};info.ArgumentList.Add(System.IO.Path.Combine(folder,"start-gateway.mjs"));info.ArgumentList.Add(args[2]);
   using var process=Process.Start(info)!;_ = process.StandardOutput.ReadToEndAsync();_ = process.StandardError.ReadToEndAsync();process.WaitForExit();return;
  }
  var app=new Application();app.Run(new SetupWindow(args[0]));
 }
}
class SetupWindow:Window {
 readonly string folder; Process? worker; readonly TextBlock status=new(){Text="正在请求官方二维码…",TextWrapping=TextWrapping.Wrap,Margin=new Thickness(12)};
 readonly Canvas canvas=new(){Width=320,Height=320,Background=Brushes.White};readonly PasswordBox code=new(){Width=150,MaxLength=12};
 public SetupWindow(string folder){this.folder=folder;Title="微信官方扫码绑定 · 飞书消息转发";Width=420;Height=580;ResizeMode=ResizeMode.NoResize;WindowStartupLocation=WindowStartupLocation.CenterScreen;Background=Brushes.White;
 var panel=new StackPanel{Margin=new Thickness(12)};panel.Children.Add(new TextBlock{Text="请用你自己的微信扫码并在手机确认",FontSize=17,TextWrapping=TextWrapping.Wrap});panel.Children.Add(status);panel.Children.Add(canvas);
 panel.Children.Add(new TextBlock{Text="二维码通常约5分钟有效。若手机要求验证码，\n仅在下方本机输入；不要发到聊天。",Margin=new Thickness(8),TextWrapping=TextWrapping.Wrap});
 var row=new StackPanel{Orientation=Orientation.Horizontal,HorizontalAlignment=HorizontalAlignment.Center};row.Children.Add(code);var submit=new Button{Content="提交验证码",Margin=new Thickness(8,0,0,0)};submit.Click+=(_,_)=>{if(worker is {HasExited:false}&&code.Password.Length>0){worker.StandardInput.WriteLine(code.Password);worker.StandardInput.Flush();code.Clear();}};row.Children.Add(submit);panel.Children.Add(row);
 var refresh=new Button{Content="二维码失效后重新请求",Margin=new Thickness(8)};refresh.Click+=(_,_)=>Start();panel.Children.Add(refresh);Content=panel;Loaded+=(_,_)=>Start();Closed+=(_,_)=>Stop();}
 void Stop(){try{if(worker is {HasExited:false})worker.Kill(entireProcessTree:true);}catch{}worker?.Dispose();worker=null;}
 async void Start(){Stop();canvas.Children.Clear();status.Text="正在请求官方二维码…";var root=System.IO.Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"FeishuWeixinForwarder");
 var info=new ProcessStartInfo(System.IO.Path.Combine(folder,"node-v22.22.3-win-x64","node.exe")){UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,RedirectStandardInput=true,WorkingDirectory=folder};info.ArgumentList.Add(System.IO.Path.Combine(folder,"setup-worker.mjs"));info.ArgumentList.Add(root);
 try{var p=Process.Start(info)!;worker=p;_ = p.StandardError.ReadToEndAsync();string? line;while((line=await p.StandardOutput.ReadLineAsync())!=null){if(worker!=p)break;using var doc=JsonDocument.Parse(line);var obj=doc.RootElement;switch(obj.GetProperty("kind").GetString()){
 case "qr":Draw(obj.GetProperty("modules"));status.Text="二维码已就绪：请立即用微信扫码并在手机确认。";break;
 case "verify":status.Text="官方流程可能需要手机验证码，请按手机提示在下方输入。";break;
 case "bound":status.Text="微信已绑定。请在微信机器人聊天中发送：\n/echo 测试123\n尚未启用真实飞书转发，先验证这条虚构消息。";canvas.Children.Clear();break;
 case "error":status.Text="绑定未完成。可重新请求二维码；未启用消息转发。";break;}}
 }catch{status.Text="扫码程序启动失败，未启用转发。";}}
 void Draw(JsonElement modules){canvas.Children.Clear();int n=modules.GetArrayLength();double scale=320.0/(n+8);for(int y=0;y<n;y++)for(int x=0;x<n;x++)if(modules[y][x].GetBoolean()){var r=new Rectangle{Width=scale+.1,Height=scale+.1,Fill=Brushes.Black};Canvas.SetLeft(r,(x+4)*scale);Canvas.SetTop(r,(y+4)*scale);canvas.Children.Add(r);}}
}
