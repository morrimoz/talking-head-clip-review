// Head yaw per frame via macOS Vision. usage: pose <video> <start> <end> <fps>  ->  "t yaw" lines ("t nan" = no face)
import AVFoundation
import Vision
let a=CommandLine.arguments
let asset=AVURLAsset(url: URL(fileURLWithPath: a[1]))
let s=Double(a[2])!, e=Double(a[3])!, fps=Double(a[4])!
let gen=AVAssetImageGenerator(asset: asset)
gen.appliesPreferredTrackTransform=true
gen.requestedTimeToleranceBefore = .zero; gen.requestedTimeToleranceAfter = .zero
var t=s
while t<e {
  if let img=try? gen.copyCGImage(at: CMTime(seconds:t,preferredTimescale:600), actualTime:nil) {
    let r=VNDetectFaceRectanglesRequest(); r.revision=VNDetectFaceRectanglesRequestRevision3
    try? VNImageRequestHandler(cgImage: img).perform([r])
    if let f=r.results?.first { print(String(format:"%.3f %.3f",t,f.yaw?.doubleValue ?? 0)) } else { print(String(format:"%.3f nan",t)) }
  }
  t+=1/fps
}
