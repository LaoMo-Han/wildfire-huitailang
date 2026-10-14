using System;
using System.Diagnostics;
using System.IO;
using System.Threading;
using System.Windows.Forms;

static class UpdateInstaller {
    static void Wait(int pid){if(pid<=0)return;try{using(var p=Process.GetProcessById(pid))p.WaitForExit();}catch(ArgumentException){}}
    [STAThread] static int Main(string[] args) {
        if(args.Length!=5)return 2;
        string root=Path.GetFullPath(args[0]),stage=Path.GetFullPath(args[1]);
        try{
            int game,launcher;if(!Int32.TryParse(args[2],out game)||!Int32.TryParse(args[3],out launcher))return 2;
            Wait(game);Wait(launcher);
            using(var mutex=UpdateCore.RootMutex(root)){
                bool locked=false;try{try{locked=mutex.WaitOne(3000);}catch(AbandonedMutexException){locked=true;}if(!locked)throw new IOException("游戏已重新打开，请退出后重试更新");UpdateCore.Apply(root,stage);}finally{if(locked)mutex.ReleaseMutex();}
            }
            UpdateCore.Atomic(Path.Combine(root,"game","update_status.json"),UpdateCore.Serializer().Serialize(new {state="installed",message="更新已安装",version=UpdateCore.Installed(root).version}));
            if(args[4]=="restart")Process.Start(new ProcessStartInfo(Path.Combine(root,"开始游戏.exe")){WorkingDirectory=root,UseShellExecute=true});
            return 0;
        }catch(Exception error){
            UpdateCore.Atomic(Path.Combine(root,"game","update_status.json"),UpdateCore.Serializer().Serialize(new {state="error",message="更新失败，旧版已保留："+error.Message}));
            MessageBox.Show("更新未能完成，旧版文件已保留。\n"+error.Message,"无尽战区更新",MessageBoxButtons.OK,MessageBoxIcon.Warning);return 1;
        }
    }
}
