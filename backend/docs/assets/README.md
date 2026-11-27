# Presentation assets

[← Documentation](../README.md)

| File | Source |
| --- | --- |
| `banner.svg` | Original vector illustration for this repository; contains no external assets |
| `extraction.png` | Actual local Streamlit upload and text-extraction result |
| `document-review.png` | Actual local review screen with fixture-derived synthetic invoice data |
| `quotation-review.png` | Actual local quotation screen showing expiry, payment terms, and passing arithmetic checks |
| `operations.png` | Actual local metrics after seeding three digital documents and one unapproved draft |
| `vendorops-demo.mp4` | Actual 2 minute 18 second browser recording of the complete synthetic local workflow |
| `demo-preview.png` | Unmodified frame from that video, showing three documents, two completed jobs, and one simulated action |
| `demo-manifest.json` | Reviewed public media metadata and observed counts derived from the isolated run receipt |

Screenshots are captured with [capture_demo.py](../../../frontend/scripts/capture_demo.py).
The script starts isolated local servers with temporary storage, fixture extraction, and live
calls/sending disabled. It approves no actions and cleans up its own processes and data.
These still screenshots demonstrate the interface, not live model accuracy or cloud deployment.

The video is produced separately with [record_demo.py](../../../frontend/scripts/record_demo.py).
It uploads a real digital PDF, uses real local Tesseract OCR, saves a human-reviewed invoice,
compares it with a fixture PO, applies a confirmed policy, edits and approves a draft, executes
one simulated delivery, checks a fixture quotation, and displays operations. No real email is sent.
The reviewed public copy contains only synthetic examples and a test address. It contains no AWS
credentials, project identifiers, private quotations, browser sign-in, or customer documents.

The video is H.264, 1440 × 1000, 25 fps, with on-screen captions and no audio. It decoded completely,
and frames were inspected before publication. The [manifest](demo-manifest.json) contains its hash
and provider provenance; the full database, run receipt, and logs remain ignored local artifacts.

See [preview instructions](../../../frontend/README.md#preview-assets) to regenerate the stills and
[recording instructions](../../../frontend/README.md#record-an-end-to-end-walkthrough) to film another run.
