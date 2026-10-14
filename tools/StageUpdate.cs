// Maintainer helper: stage a first updater installation for a legacy local
// development client. It never changes game files while either process runs.
using System;
using System.Diagnostics;
using System.IO;

static class StageUpdate {
    static int Main(string[] args){
        if(args.Length!=4)return 2;
        string root=Path.GetFullPath(args[0]),helperSource=Path.GetFullPath(args[1]);
        int game=int.Parse(args[2]),launcher=int.Parse(args[3]);
        var manifest=UpdateCore.Fetch();
        string stage=UpdateCore.Prepare(root,manifest,(c,p)=>Console.WriteLine(c+" "+p+"%"));
        string helper=Path.Combine(stage,"apply.exe");File.Copy(helperSource,helper);File.Copy(helperSource+".config",helper+".config");
        Process.Start(new ProcessStartInfo(helper,"\""+root+"\" \""+stage+"\" "+game+" "+launcher+" close"){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,WindowStyle=ProcessWindowStyle.Hidden});
        Console.WriteLine("Staged "+manifest.version+"; waiting for the existing game and launcher to exit.");
        return 0;
    }
}
