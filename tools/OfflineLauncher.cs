using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;
using System.Threading;
using System.Collections.Generic;
using System.Xml;

// Client 1.0.192 parses "-redirect <decimal HWND>" and checks IsWindow.
// The local message endpoint has no visible UI and stays alive with the child.
sealed class OfflineLauncher : NativeWindow
{
    private Process client;
    private System.Windows.Forms.Timer timer;
    private string root;
    private int busy;
    private string requestId;
    private UpdateManifest available;
    private string readyStage;
    private bool restart;
    private volatile bool cancelDownload;
    private DateTime nextCheck=DateTime.MinValue;
    private readonly object statusLock=new object();
    private OfflineLauncher(string root)
    {
        this.root=root;
        UpdateCore.Recover(root);
        ConfigureOffline();
        try{requestId=UpdateCore.Read<Dictionary<string,object>>(Path.Combine(root,"game","update_request.json"))["id"].ToString();}catch{}
        CreateParams parameters = new CreateParams();
        parameters.Caption = "tw2launch";
        parameters.Width = parameters.Height = 1;
        parameters.Style = unchecked((int)0x80000000);
        CreateHandle(parameters);
        string executable = Path.Combine(root, "game", "wf.exe");
        ProcessStartInfo start = new ProcessStartInfo(executable);
        start.WorkingDirectory = Path.GetDirectoryName(executable);
        start.Arguments = "-redirect " + Handle.ToInt64().ToString();
        start.UseShellExecute = false;
        client = Process.Start(start);
        timer = new System.Windows.Forms.Timer();
        timer.Interval = 500;
        timer.Tick += delegate {
            PollUpdates();
            if (client.HasExited) {
                if(readyStage!=null)StartInstaller();
                timer.Stop();
                DestroyHandle();
                client.Dispose();
                Application.ExitThread();
            }
        };
        timer.Start();
    }

    private void ConfigureOffline(){
        string path=Path.Combine(root,"game","conf.xml");if(!File.Exists(path))return;
        var doc=new XmlDocument();doc.XmlResolver=null;
        using(var reader=XmlReader.Create(path,new XmlReaderSettings{DtdProcessing=DtdProcessing.Prohibit,XmlResolver=null}))doc.Load(reader);
        bool changed=false;var agreement=doc.DocumentElement.SelectSingleNode("UserProtocol");if(agreement!=null){agreement.ParentNode.RemoveChild(agreement);changed=true;}
        foreach(var pair in new Dictionary<string,string>{{"login/ip","127.0.0.1"},{"login/servers/server0","0 0 0 0 Offline Offline 127.0.0.1:20160 127.0.0.1:20160 127.0.0.1:20160"}}){var node=doc.DocumentElement.SelectSingleNode(pair.Key);if(node!=null&&node.InnerText!=pair.Value){node.InnerText=pair.Value;changed=true;}}
        if(changed)UpdateCore.Atomic(path,doc.OuterXml);
    }

    private void Status(string state,string message,int progress=0){lock(statusLock){try{var installed=UpdateCore.Installed(root);UpdateCore.Atomic(Path.Combine(root,"game","update_status.json"),UpdateCore.Serializer().Serialize(new {request_id=requestId,state=state,message=message,progress=progress,current_version=installed.version,version=available==null?installed.version:available.version,notes=available==null?"":available.notes}));}catch(IOException){}catch(UnauthorizedAccessException){}}}
    private void Background(Action action){if(Interlocked.CompareExchange(ref busy,1,0)!=0)return;ThreadPool.QueueUserWorkItem(delegate{try{action();}catch(Exception error){Status("error","暂时无法更新，仍可玩旧版："+error.Message);}finally{Interlocked.Exchange(ref busy,0);}});}
    private void Check(){Status("checking","正在检查更新");var m=UpdateCore.Fetch();if(m.build>UpdateCore.Installed(root).build){available=m;Status("available","有新版本，点击下载更新");}else{available=null;Status("current","已经是最新版本");}}
    private void Download(){cancelDownload=false;if(available==null)Check();if(available==null)return;readyStage=UpdateCore.Prepare(root,available,(component,p)=>{if(cancelDownload)throw new OperationCanceledException("下载已取消");Status("downloading","正在下载 "+component,p);});Status("ready","下载完成，退出游戏后安装");}
    private void PollUpdates(){
        if(DateTime.UtcNow>=nextCheck&&readyStage==null){nextCheck=DateTime.UtcNow.AddMinutes(5);Background(Check);}
        try{var r=UpdateCore.Read<Dictionary<string,object>>(Path.Combine(root,"game","update_request.json"));var id=r["id"].ToString();if(id==requestId)return;requestId=id;var action=r["action"].ToString();
            if(action=="check")Background(Check);
            else if(action=="download")Background(Download);
            else if(action=="feedback")Process.Start(new ProcessStartInfo(UpdateCore.Site+"?version="+Uri.EscapeDataString(UpdateCore.Installed(root).version)+"#feedback"){UseShellExecute=true});
            else if(action=="install"&&readyStage!=null)restart=true;
            else if(action=="cancel")cancelDownload=true;
        }catch(FileNotFoundException){}catch(DirectoryNotFoundException){}catch(Exception error){Status("error",error.Message);}
    }
    private void StartInstaller(){
        var helper=Path.Combine(readyStage,"apply.exe");File.Copy(Path.Combine(root,"update.exe"),helper,true);File.Copy(Path.Combine(root,"update.exe.config"),helper+".config",true);
        var args="\""+root.TrimEnd(Path.DirectorySeparatorChar)+"\" \""+readyStage+"\" "+client.Id+" "+Process.GetCurrentProcess().Id+" "+(restart?"restart":"close");
        Process.Start(new ProcessStartInfo(helper,args){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden});
    }

    [STAThread]
    static int Main()
    {
        string root = Path.GetFullPath(AppDomain.CurrentDomain.BaseDirectory).TrimEnd(Path.DirectorySeparatorChar);
        string errorLog = Path.Combine(root, "game", "offline_launcher_error.log");
        try {
            if (File.Exists(errorLog)) File.Delete(errorLog);
            File.Copy(Path.Combine(root, "bootstrap", "EditorConf.py"),
                      Path.Combine(root, "res", "editor", "client", "EditorConf.py"), true);
            using(var mutex=UpdateCore.RootMutex(root)){
                bool locked=false;try{try{locked=mutex.WaitOne(0);}catch(AbandonedMutexException){locked=true;}if(!locked)return 0;
                    OfflineLauncher launcher = new OfflineLauncher(root);
                    Application.Run();GC.KeepAlive(launcher);
                }finally{if(locked)mutex.ReleaseMutex();}
            }
            return 0;
        } catch (Exception error) {
            File.WriteAllText(errorLog, error.ToString());
            return 1;
        }
    }
}
