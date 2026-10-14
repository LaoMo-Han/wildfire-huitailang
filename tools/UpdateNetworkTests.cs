using System;
using System.IO;
using System.Linq;

static class UpdateNetworkTests {
    static void Assert(bool value,string message){if(!value)throw new Exception(message);Console.WriteLine("PASS "+message);}
    static int Main(string[] args){
        string directory=Path.GetFullPath(args[0]);Directory.CreateDirectory(directory);
        var manifest=UpdateCore.Fetch();var component=manifest.components.First(c=>c.id=="runtime");
        var file=Path.Combine(directory,"runtime.zip");UpdateCore.Download(component,file,p=>{});
        Assert(UpdateCore.Hash(file)==component.sha256,"real HTTPS component downloaded and verified");
        string original=component.sha256;component.sha256=new string('0',64);
        try{UpdateCore.Download(component,Path.Combine(directory,"damaged.zip"),p=>{});throw new Exception("Expected hash mismatch");}catch(InvalidDataException){}
        Assert(!File.Exists(Path.Combine(directory,"damaged.zip"))&&!File.Exists(Path.Combine(directory,"damaged.zip.part")),"wrong expected hash rejected and partial download removed");
        component.sha256=original;
        try{UpdateCore.Download(component,Path.Combine(directory,"cancelled.zip"),p=>{throw new OperationCanceledException();});throw new Exception("Expected cancellation");}catch(OperationCanceledException){}
        Assert(!File.Exists(Path.Combine(directory,"cancelled.zip"))&&!File.Exists(Path.Combine(directory,"cancelled.zip.part")),"download interruption cleans partial file");
        UpdateCore.Download(component,Path.Combine(directory,"retry.zip"),p=>{});
        Assert(UpdateCore.Hash(Path.Combine(directory,"retry.zip"))==original,"retry after interruption succeeds");
        return 0;
    }
}
