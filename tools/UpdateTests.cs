using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;

static class UpdateTests {
    static void Assert(bool value,string message){if(!value)throw new Exception(message);Console.WriteLine("PASS "+message);}
    static UpdateManifest Fixture(string stage,long build,string content){
        var m=new UpdateManifest{schema_version=1,base_client="1.0.192",version="test."+build,build=build,remove=new List<string>(),components=new List<UpdateComponent>()};
        foreach(var group in new[]{new[]{"core","game/wf.exe"},new[]{"runtime","res/editor/client/offline_runtime.py"},new[]{"launcher","launch.exe"}}){
            var target=UpdateCore.Inside(Path.Combine(stage,"payload"),group[1]);Directory.CreateDirectory(Path.GetDirectoryName(target));File.WriteAllText(target,content+group[0]);
            var zip=Path.Combine(stage,group[0]+".zip");Directory.CreateDirectory(stage);using(var z=ZipFile.Open(zip,ZipArchiveMode.Create))z.CreateEntryFromFile(target,group[1]);
            m.components.Add(new UpdateComponent{id=group[0],url="https://github.com/LaoMo-Han/wildfire-downloads/releases/download/test/"+group[0]+".zip",size=new FileInfo(zip).Length,sha256=UpdateCore.Hash(zip),files=new Dictionary<string,string>{{group[1],UpdateCore.Hash(target)}}});
        }
        UpdateCore.Atomic(Path.Combine(stage,"manifest.json"),UpdateCore.Serializer().Serialize(m));return m;
    }
    static int Main(string[] args){
        string root=Path.GetFullPath(args[0]);if(Directory.Exists(root))throw new Exception("Use a new test directory");Directory.CreateDirectory(Path.Combine(root,"game"));
        File.WriteAllText(Path.Combine(root,"game","conf.xml"),"personal resolution");File.WriteAllText(Path.Combine(root,"game","offline_profile.json"),"personal hero");
        Assert(!UpdateCore.Allowed("../outside.py")&&!UpdateCore.Allowed("game/conf.xml")&&!UpdateCore.Allowed("res/editor/client/x.py:ads")&&!UpdateCore.Allowed("res/editor/client/../x.py"),"protected paths and traversal rejected");
        var stage=Path.Combine(root,".updates","1-"+Guid.NewGuid().ToString("N"));var first=Fixture(stage,1,"first-");UpdateCore.Validate(first);
        foreach(var c in first.components)UpdateCore.Extract(Path.Combine(stage,c.id+".zip"),c,stage);
        UpdateCore.Apply(root,stage);
        Assert(UpdateCore.Installed(root).build==1,"install writes version after verified files");
        Assert(File.ReadAllText(Path.Combine(root,"game","conf.xml"))=="personal resolution"&&File.ReadAllText(Path.Combine(root,"game","offline_profile.json"))=="personal hero","player settings preserved");
        Assert(!first.components.Any(c=>UpdateCore.Needed(root,c)),"unchanged components need no download");
        var secondStage=Path.Combine(root,".updates","2-"+Guid.NewGuid().ToString("N"));var second=Fixture(secondStage,2,"second-");
        try{UpdateCore.Apply(root,secondStage,true);throw new Exception("Expected injected failure");}catch(IOException){}
        Assert(UpdateCore.Installed(root).build==1&&File.ReadAllText(Path.Combine(root,"game","wf.exe"))=="first-core","partial apply rolled back including version");
        // Model a power loss after replacement but before the version commit.
        var journalPath=Path.Combine(root,".updates","journal.json");var journal=UpdateCore.Read<ApplyJournal>(journalPath);journal.state="applying";UpdateCore.Atomic(journalPath,UpdateCore.Serializer().Serialize(journal));File.WriteAllText(Path.Combine(root,"game","wf.exe"),"interrupted");UpdateCore.Recover(root);
        Assert(File.ReadAllText(Path.Combine(root,"game","wf.exe"))=="first-core","interrupted journal recovered");
        UpdateCore.Apply(root,secondStage);
        Assert(UpdateCore.Installed(root).build==2,"subsequent update succeeds after recovery");
        var evil=Path.Combine(root,"evil.zip");using(var z=ZipFile.Open(evil,ZipArchiveMode.Create)){using(var s=new StreamWriter(z.CreateEntry("../outside.py").Open()))s.Write("bad");}
        try{UpdateCore.Extract(evil,first.components[1],Path.Combine(root,".updates","bad"));throw new Exception("Expected unsafe zip rejection");}catch(InvalidDataException){}
        Assert(!File.Exists(Path.Combine(root,"outside.py")),"unsafe archive did not escape staging");
        var damagedStage=Path.Combine(root,".updates","3-"+Guid.NewGuid().ToString("N"));var damaged=Fixture(damagedStage,3,"third-");File.WriteAllText(Path.Combine(damagedStage,"payload","launch.exe"),"damaged");
        try{UpdateCore.Apply(root,damagedStage);throw new Exception("Expected hash rejection");}catch(InvalidDataException){}
        Assert(UpdateCore.Installed(root).build==2,"corrupt staging rejected before installation");
        File.WriteAllText(Path.Combine(damagedStage,"payload","launch.exe"),"third-launcher");
        try{UpdateCore.Apply(root,damagedStage,false,0);throw new Exception("Expected disk space rejection");}catch(IOException){}
        Assert(UpdateCore.Installed(root).build==2&&File.ReadAllText(Path.Combine(root,"game","wf.exe"))=="second-core","insufficient space rejected before changing files");
        using(var locked=File.Open(Path.Combine(root,"launch.exe"),FileMode.Open,FileAccess.Read,FileShare.Read)){
            try{UpdateCore.Apply(root,damagedStage);throw new Exception("Expected locked file rejection");}catch(IOException){}
            Assert(File.ReadAllText(Path.Combine(root,"game","wf.exe"))=="second-core","locked later component leaves earlier files untouched");
        }
        var jumpStage=Path.Combine(root,".updates","5-"+Guid.NewGuid().ToString("N"));Fixture(jumpStage,5,"fifth-");UpdateCore.Apply(root,jumpStage);
        Assert(UpdateCore.Installed(root).build==5&&File.ReadAllText(Path.Combine(root,"game","wf.exe"))=="fifth-core","complete components support skipping multiple versions");
        return 0;
    }
}
