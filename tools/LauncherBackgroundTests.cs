using System;
using System.IO;
using System.Reflection;
using System.Runtime.Serialization;
using System.Threading;

// No windows or network requests: exercise the real launcher's background boundary.
static class LauncherBackgroundTests
{
    static readonly BindingFlags Fields=BindingFlags.Instance|BindingFlags.NonPublic;
    static object launcher;
    static Type type=typeof(OfflineLauncher);
    static void Set(string name,object value){type.GetField(name,Fields).SetValue(launcher,value);}
    static int Busy(){return (int)type.GetField("busy",Fields).GetValue(launcher);}
    static void Run(Action action){type.GetMethod("Background",Fields).Invoke(launcher,new object[]{action});}
    static void Wait(){for(int i=0;i<200&&Busy()!=0;i++)Thread.Sleep(10);if(Busy()!=0)throw new Exception("Background did not finish");}
    static void Assert(bool value,string text){if(!value)throw new Exception(text);Console.WriteLine("PASS "+text);}
    static int Main(string[] args)
    {
        string root=Path.GetFullPath(args[0]);Directory.CreateDirectory(Path.Combine(root,"game"));
        launcher=FormatterServices.GetUninitializedObject(type);
        Set("root",root);Set("statusLock",new object());Set("requestId","failure-test");
        Run(delegate{throw new IOException("simulated unavailable network");});Wait();
        var status=UpdateCore.Read<System.Collections.Generic.Dictionary<string,object>>(Path.Combine(root,"game","update_status.json"));
        Assert(status["state"].ToString()=="error"&&Busy()==0,"network failure remains a status result and releases busy flag");
        using(var gate=new ManualResetEvent(false)){
            int runs=0;Run(delegate{Interlocked.Increment(ref runs);gate.WaitOne();});
            Run(delegate{Interlocked.Increment(ref runs);});gate.Set();Wait();
            Assert(runs==1,"overlapping update requests do not start competing workers");
        }
        File.Delete(Path.Combine(root,"game","update_status.json"));Directory.CreateDirectory(Path.Combine(root,"game","update_status.json"));
        Run(delegate{throw new IOException("simulated failure while status path is unwritable");});Wait();
        Assert(Busy()==0,"status write failure also leaves launcher alive");
        return 0;
    }
}
