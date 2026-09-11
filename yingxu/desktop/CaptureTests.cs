using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace YingXu.Desktop
{
    internal static class CaptureTests
    {
        private const string Project="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        private const string Item="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        private static int passed;
        private static readonly JavaScriptSerializer Json=new JavaScriptSerializer();
        private static void Check(bool value,string name) { if(!value)throw new Exception("FAILED: "+name); passed++; Console.WriteLine("PASS "+name); }
        private static Dictionary<string,object> Context(string request,string project=Project,string item=Item)
        {
            return new Dictionary<string,object>{{"action","capture-context"},{"requestId",request},{"projectId",project},{"itemId",item}};
        }
        private static Bitmap Picture(int width=64,int height=32)
        {
            var image=new Bitmap(width,height); using(var graphics=Graphics.FromImage(image))graphics.Clear(Color.FromArgb(46,120,78));return image;
        }
        private sealed class Fixture : IDisposable
        {
            internal CaptureCoordinator Coordinator;
            internal CaptureServices Services;
            internal int Screens,Selections,Copies,Uploads;
            internal bool Reply=true,Deliver=true,Cancel,CopyFails,UploadFails;
            internal string Target=Project,Request;
            internal readonly List<CaptureResult> Results=new List<CaptureResult>();
            internal Fixture()
            {
                Services=new CaptureServices {
                    ScreenBounds=()=>{Screens++;return new Rectangle(-100,20,64,32);},
                    Select=bounds=>{Selections++;Check(bounds.X==-100,"locked screen keeps negative physical origin");return Cancel?null:Picture();},
                    Copy=image=>{Copies++;if(CopyFails)throw new IOException("clipboard busy");},
                    Upload=(image,project)=>{Uploads++;Check(project==Project,"attachment uses locked project");if(UploadFails)throw new IOException("upload failed");return new {id=Item,project_id=Project,kind="image"};}
                };
                Coordinator=new CaptureCoordinator(message=>{
                    var result=message as CaptureResult;
                    if(result!=null){if(Deliver)Results.Add(result);return Deliver;}
                    var payload=Json.Deserialize<Dictionary<string,object>>(Json.Serialize(message));Request=(string)payload["requestId"];
                    if(Reply)Check(Coordinator.Receive(Context(Request,Target)),"matching context accepted");return true;
                },(message,error)=>{},Services);
                Coordinator.ContextTimeoutMs=15;
            }
            public void Dispose(){Coordinator.Dispose();}
        }
        private static async Task Workflow()
        {
            using(var f=new Fixture())
            {
                Check(f.Screens==0&&f.Selections==0&&!f.Coordinator.Busy,"idle coordinator has no screen reads or bitmap allocation");
                await f.Coordinator.StartAsync();Check(f.Copies==1&&f.Uploads==1&&f.Results[0].clipboardCopied&&f.Results[0].item!=null,"clipboard and attachment independently complete");
                Check(!f.Coordinator.Receive(Context(f.Request)),"late context after completion rejected");
            }
            using(var f=new Fixture()){f.Target=null;await f.Coordinator.StartAsync();Check(f.Copies==1&&f.Uploads==0&&f.Results[0].saveError!=null,"empty project copies without guessing a target");}
            using(var f=new Fixture()){f.Reply=false;await f.Coordinator.StartAsync();Check(f.Selections==1&&f.Copies==1&&f.Uploads==0,"finite context timeout still permits clipboard capture");}
            using(var f=new Fixture()){f.Cancel=true;await f.Coordinator.StartAsync();Check(f.Results[0].cancelled&&f.Copies==0&&f.Uploads==0,"cancelled selection does not touch clipboard or project");}
            using(var f=new Fixture()){f.CopyFails=true;await f.Coordinator.StartAsync();Check(!f.Results[0].clipboardCopied&&f.Results[0].clipboardError!=null&&f.Results[0].item!=null,"clipboard failure preserves successful attachment");}
            using(var f=new Fixture()){f.UploadFails=true;await f.Coordinator.StartAsync();Check(f.Results[0].clipboardCopied&&f.Results[0].saveError!=null&&f.Results[0].item==null,"upload failure preserves clipboard success");}
            using(var f=new Fixture())
            {
                f.Reply=false;var first=f.Coordinator.StartAsync();await f.Coordinator.StartAsync();Check(f.Screens==1,"single-task gate rejects repeated triggers");
                Check(!f.Coordinator.Receive(Context("stale")),"stale handshake cannot redirect capture");
                Check(f.Coordinator.Receive(Context(f.Request)),"current handshake completes pending capture");await first;
            }
            using(var f=new Fixture()){f.Deliver=false;await f.Coordinator.StartAsync();Check(f.Results.Count==0,"unready frontend retains result metadata");f.Deliver=true;f.Coordinator.Flush();f.Coordinator.Flush();Check(f.Results.Count==1,"queued capture result delivered exactly once after ready");}
            using(var f=new Fixture()){f.Reply=false;var pending=f.Coordinator.StartAsync();f.Coordinator.Dispose();await pending;Check(f.Selections==0&&f.Results.Count==0,"disposal during handshake prevents screen capture");}
            using(var f=new Fixture()){f.Services.Select=bounds=>{throw new IOException("synthetic capture failure");};await f.Coordinator.StartAsync();Check(!f.Coordinator.Busy&&f.Results[0].error.Contains("synthetic capture failure"),"capture failure releases busy gate");}
        }
        private static void GeometryAndHotkeys()
        {
            uint modifiers,key;
            Check(CaptureHotkey.TryParse(CaptureHotkey.Default,out modifiers,out key)&&modifiers==0x4007&&key=='S',"default hotkey has no-repeat modifiers");
            Check(CaptureHotkey.TryParse("Shift+Ctrl+F24",out modifiers,out key)&&key==0x87,"custom modifier order and F24 supported");
            foreach(string value in new[]{"Win+Shift+S","Ctrl+S","Ctrl+Alt+F12","Ctrl+Ctrl+S","Ctrl+Alt+F25","Ctrl+Alt+é","Ctrl+Alt+F01"})
                Check(!CaptureHotkey.TryParse(value,out modifiers,out key),"reserved or malformed hotkey rejected");
            int registered=0,removed=0;bool available=true;
            using(var hotkey=new CaptureHotkey((h,id,m,k)=>{registered++;return available;},(h,id)=>removed++))
            {
                Check(hotkey.Configure(new IntPtr(1),true,CaptureHotkey.Default)==null&&hotkey.Registered,"hotkey registration succeeds");
                hotkey.Configure(new IntPtr(1),true,CaptureHotkey.Default);Check(registered==1,"unchanged settings do not register twice");
                available=false;Check(hotkey.Configure(new IntPtr(1),true,"Ctrl+Shift+F10")!=null&&!hotkey.Registered&&removed==1,"occupied hotkey leaves disabled state and explains conflict");
                hotkey.Configure(new IntPtr(1),false,CaptureHotkey.Default);Check(registered==2,"disabled hotkey has no registration work");
            }
            CaptureContext context;
            Check(CaptureContext.TryRead(Context("r",null),"r",out context)&&context.ProjectId==null&&context.ItemId==null,"empty project also clears insertion item");
            Check(!CaptureContext.TryRead(Context("r","../../secret"),"r",out context),"context rejects arbitrary project path");
            var extra=Context("r");extra["path"]="not allowed";Check(!CaptureContext.TryRead(extra,"r",out context),"context rejects extra path field");
            Check(CapturePlatform.Selection(new Point(80,40),new Point(-5,-10),new Size(64,32))==new Rectangle(0,0,64,32),"reverse drag clamps to the original screen only");
            using(var image=Picture())
            {
                image.SetPixel(8,9,Color.Red);
                using(var crop=CapturePlatform.Crop(image,new Rectangle(8,9,10,11)))
                {
                    Check(crop.Width==10&&crop.Height==11&&crop.GetPixel(0,0).ToArgb()==Color.Red.ToArgb(),"crop uses exact bitmap pixels without DPI scaling");
                    byte[] png=CapturePlatform.Encode(crop);using(var stream=new MemoryStream(png))using(var decoded=new Bitmap(stream))Check(decoded.GetPixel(0,0).ToArgb()==Color.Red.ToArgb(),"PNG roundtrip preserves synthetic pixels");
                }
                Check(CapturePlatform.Crop(image,new Rectangle(0,0,1,1))==null&&CapturePlatform.Crop(image,new Rectangle(-1,0,10,10))==null,"empty or out-of-screen regions are rejected");
            }
        }
        private static async Task UploadProtocol()
        {
            var listener=new TcpListener(IPAddress.Loopback,0);listener.Start();Hub.Url="http://127.0.0.1:"+((IPEndPoint)listener.LocalEndpoint).Port+"/";
            byte[] png;using(var image=Picture())png=CapturePlatform.Encode(image);
            var server=Task.Run(()=>{
                for(int requestIndex=0;requestIndex<2;requestIndex++)using(var client=listener.AcceptTcpClient())using(var stream=client.GetStream())
                {
                    client.ReceiveTimeout=5000;var header=new List<byte>();int value;
                    while((value=stream.ReadByte())>=0){header.Add((byte)value);int n=header.Count;if(n>=4&&header[n-4]==13&&header[n-3]==10&&header[n-2]==13&&header[n-1]==10)break;if(n>16384)throw new IOException("fixture header too long");}
                    string text=Encoding.ASCII.GetString(header.ToArray());
                    if(text.IndexOf("Expect: 100-continue",StringComparison.OrdinalIgnoreCase)>=0){byte[] interim=Encoding.ASCII.GetBytes("HTTP/1.1 100 Continue\r\n\r\n");stream.Write(interim,0,interim.Length);}
                    if(requestIndex==1)
                    {
                        Check(text.Contains("POST /api/upload?project="+Project+"&category=references&name="),"binary upload uses project reference attachment endpoint");
                        Check(text.Contains("Origin: "+Hub.Url.TrimEnd('/'))&&text.Contains("X-YingXu-Token: fixture-token"),"upload carries same-origin and fresh fixture token");
                        var body=new byte[png.Length];int read=0;while(read<body.Length){int n=stream.Read(body,read,body.Length-read);if(n==0)throw new IOException("short upload");read+=n;}
                        Check(Convert.ToBase64String(body)==Convert.ToBase64String(png),"PNG is sent as original binary bytes");
                    }
                    string json=requestIndex==0?"{\"token\":\"fixture-token\"}":Json.Serialize(new{id=Item,project_id=Project,kind="image"});
                    byte[] data=Encoding.UTF8.GetBytes(json),headers=Encoding.ASCII.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "+data.Length+"\r\nConnection: close\r\n\r\n");stream.Write(headers,0,headers.Length);stream.Write(data,0,data.Length);
                }
            });
            try{var result=await Task.Run(()=>DesktopApi.UploadCapture(png,Project));await server;Check(result is Dictionary<string,object>,"upload returns the resource metadata directly");}finally{listener.Stop();}
        }
        private static void SelectorEvents()
        {
            Action<CaptureSelector,string,object> fire=(form,method,args)=>typeof(CaptureSelector).GetMethod(method,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(form,new[]{args});
            using(var image=Picture(640,480))
            using(var selector=new CaptureSelector(image,new Rectangle(100,100,640,480),"quick"))
            using(var painted=new Bitmap(640,480))
            {
                fire(selector,"OnMouseDown",new MouseEventArgs(MouseButtons.Left,1,100,100,0));
                fire(selector,"OnMouseMove",new MouseEventArgs(MouseButtons.Left,0,300,300,0));
                selector.DrawToBitmap(painted,new Rectangle(0,0,640,480));
                Check(selector.Area==new Rectangle(100,100,200,200),"native selector mouse events produce expected pixel region");
                Check(painted.GetPixel(150,150).ToArgb()==image.GetPixel(150,150).ToArgb()&&painted.GetPixel(500,400).G<image.GetPixel(500,400).G,"native selector preserves selected pixels and shades only outside synthetic image");
                fire(selector,"OnMouseUp",new MouseEventArgs(MouseButtons.Left,1,300,300,0));
                Check(selector.DialogResult==DialogResult.OK,"native selector mouse release confirms region");
            }
            using(var image=Picture())using(var selector=new CaptureSelector(image,new Rectangle(100,100,64,32)))
            {
                fire(selector,"OnKeyDown",new KeyEventArgs(Keys.Escape));
                Check(selector.DialogResult==DialogResult.Cancel,"native selector Escape cancels without output");
            }
        }
        private static void Fire(CaptureSelector selector,string method,object args)
        {
            typeof(CaptureSelector).GetMethod(method,BindingFlags.Instance|BindingFlags.NonPublic).Invoke(selector,new[]{args});
        }
        private static void Drag(CaptureSelector selector,Point first,Point last)
        {
            Fire(selector,"OnMouseDown",new MouseEventArgs(MouseButtons.Left,1,first.X,first.Y,0));
            Fire(selector,"OnMouseMove",new MouseEventArgs(MouseButtons.Left,0,last.X,last.Y,0));
            Fire(selector,"OnMouseUp",new MouseEventArgs(MouseButtons.Left,1,last.X,last.Y,0));
        }
        private static async Task AnnotationWorkflow()
        {
            foreach(string tool in new[]{"pen","arrow","rectangle"})
            using(var image=Picture(640,480))using(var selector=new CaptureSelector(image,new Rectangle(-640,0,640,480)))
            {
                Drag(selector,new Point(50,60),new Point(350,260));
                Check(selector.Annotating&&selector.DialogResult==DialogResult.None&&selector.CreateResult()==null,"default mode stops after selection until explicit confirmation");
                selector.DrawingTool=tool;selector.DrawingColor=Color.Blue;selector.DrawingWidth=8;
                Drag(selector,new Point(100,100),new Point(200,tool=="rectangle"?180:100));
                selector.DrawingColor=Color.Red;selector.DrawingWidth=2;
                Drag(selector,new Point(100,210),new Point(200,210));
                Check(selector.StrokeCount==2,"annotation stores separate undoable strokes: "+tool);
                selector.UndoStroke();Check(selector.StrokeCount==1,"undo removes only the latest annotation");
                selector.Confirm();using(var result=selector.CreateResult())
                {
                    Check(result.Width==300&&result.Height==200,"annotation crop retains physical selected pixel size");
                    Color marked=result.GetPixel(100,40);
                    Check(marked.B>200&&marked.R<50,"confirmed crop contains selected annotation color and geometry: "+tool);
                    Check(result.GetPixel(100,150).ToArgb()==image.GetPixel(150,210).ToArgb(),"undo restores original pixels instead of painting over them");
                }
                Check(image.GetPixel(150,100).ToArgb()==Color.FromArgb(46,120,78).ToArgb(),"annotation never mutates the original frozen bitmap");
            }
            using(var image=Picture(640,480))using(var selector=new CaptureSelector(image,new Rectangle(0,0,640,480)))
            {
                Drag(selector,new Point(50,60),new Point(350,260));Drag(selector,new Point(100,100),new Point(800,900));
                Check(selector.StrokeCount==1,"drawing outside screen clamps to the selected region");
                Fire(selector,"OnMouseDown",new MouseEventArgs(MouseButtons.Left,1,120,120,0));
                Fire(selector,"OnKeyDown",new KeyEventArgs(Keys.Control|Keys.Z));
                Check(selector.StrokeCount==1&&!selector.Capture,"undo during a held stroke cancels it and releases mouse capture without losing committed marks");
                Fire(selector,"OnKeyDown",new KeyEventArgs(Keys.Escape));
                Check(selector.DialogResult==DialogResult.Cancel&&selector.CreateResult()==null,"Escape after annotation never produces an output bitmap");
            }
            using(var image=Picture(640,480))using(var selector=new CaptureSelector(image,new Rectangle(0,0,640,480)))
            {
                Drag(selector,new Point(50,60),new Point(350,260));
                Fire(selector,"OnMouseDown",new MouseEventArgs(MouseButtons.Left,1,100,100,0));selector.Capture=false;
                Check(selector.StrokeCount==0,"lost mouse capture discards an incomplete mark");
                object[] args={new Message(),Keys.Escape};
                bool consumed=(bool)typeof(CaptureSelector).GetMethod("ProcessCmdKey",BindingFlags.Instance|BindingFlags.NonPublic).Invoke(selector,args);
                Check(consumed&&selector.DialogResult==DialogResult.Cancel&&selector.CreateResult()==null,"toolbar command processing consumes Escape and cancels before output");
            }
            using(var f=new Fixture())
            {
                f.Services.Select=bounds=>{using(var image=Picture(640,480))using(var selector=new CaptureSelector(image,new Rectangle(0,0,640,480))) {
                    Drag(selector,new Point(50,60),new Point(350,260));Drag(selector,new Point(100,100),new Point(200,100));Fire(selector,"OnKeyDown",new KeyEventArgs(Keys.Escape));return selector.CreateResult(); }};
                await f.Coordinator.StartAsync();Check(f.Copies==0&&f.Uploads==0&&f.Results[0].cancelled,"annotation cancellation reaches coordinator without clipboard or upload side effects");
            }
            using(var f=new Fixture())
            {
                f.Reply=false;f.Coordinator.Mode="quick";f.Services.Select=null;string received=null;
                f.Services.SelectMode=(bounds,mode)=>{received=mode;return null;};
                var task=f.Coordinator.StartAsync();f.Coordinator.Mode="annotate";f.Coordinator.Receive(Context(f.Request));await task;
                Check(received=="quick","capture locks configured mode before asynchronous context handshake");
            }
        }
        [STAThread]
        private static int Main(string[] args)
        {
            WindowsFormsSynchronizationContext.AutoInstall=false;
            if(args.Length==3&&args[0]=="--upload-fixture")
            {
                Uri url;if(!Uri.TryCreate(args[1],UriKind.Absolute,out url)||url.Scheme!="http"||url.Host!="127.0.0.1")throw new ArgumentException("Fixture must use loopback HTTP");
                Hub.Url=url.AbsoluteUri;using(var image=Picture(128,64))Console.WriteLine(Json.Serialize(DesktopApi.UploadCapture(CapturePlatform.Encode(image),args[2])));return 0;
            }
            GeometryAndHotkeys();SelectorEvents();Workflow().GetAwaiter().GetResult();AnnotationWorkflow().GetAwaiter().GetResult();UploadProtocol().GetAwaiter().GetResult();
            var timer=Stopwatch.StartNew();long bytes;
            using(var image=Picture(3840,2160)){using(var region=CapturePlatform.Crop(image,new Rectangle(100,100,1920,1080)))bytes=CapturePlatform.Encode(region).Length;}
            Console.WriteLine("synthetic_4k_crop_png_ms="+timer.ElapsedMilliseconds+" png_bytes="+bytes+" full_frame_bytes="+(3840L*2160*4));
            Console.WriteLine("Capture tests passed: "+passed+"; no screen or clipboard content read or changed.");return 0;
        }
    }
}
