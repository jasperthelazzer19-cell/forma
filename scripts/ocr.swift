// Single-image OCR helper. Usage: ocr <image-path>
// Prints recognized text (one logical line per VNRecognizedTextObservation).
import Vision
import AppKit
import Foundation

guard CommandLine.arguments.count >= 2 else {
    FileHandle.standardError.write("usage: ocr <path>\n".data(using: .utf8)!)
    exit(1)
}
let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let img = NSImage(contentsOf: url),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("could not load image: \(url.path)\n".data(using: .utf8)!)
    exit(2)
}
let sem = DispatchSemaphore(value: 0)
let req = VNRecognizeTextRequest { request, error in
    let obs = request.results as? [VNRecognizedTextObservation] ?? []
    for o in obs {
        if let s = o.topCandidates(1).first {
            print(s.string)
        }
    }
    sem.signal()
}
req.recognitionLevel = .accurate
req.usesLanguageCorrection = true
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([req])
} catch {
    FileHandle.standardError.write("\(error)\n".data(using: .utf8)!)
    exit(3)
}
sem.wait()
