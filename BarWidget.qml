import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui

// A compact, polling widget for Yahoo Finance's CL=F (front-month WTI)
// contract. The helper owns HTTP parsing and the alert cooldown so that this
// QML file stays focused on shell integration and presentation.
BarWidget {
  id: root
  moduleName: "io.github.17xhw.wti-oil-price"

  property string label: "WTI …"
  property string tooltip: "Loading WTI crude-oil futures price…"
  property string lastError: ""

  readonly property int refreshSeconds: Math.max(15, parseInt(setting("refreshSeconds", 30), 10) || 30)
  readonly property string helperPath: Qt.resolvedUrl("scripts/wti_oil_price.py").toString().replace("file://", "")

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function refresh() {
    if (!fetchProcess.running) fetchProcess.running = true
  }

  Timer {
    interval: root.refreshSeconds * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh()
  }

  Process {
    id: fetchProcess
    command: ["python3", root.helperPath]
    stdout: StdioCollector {
      id: fetchOutput
      waitForEnd: true
    }
    stderr: StdioCollector {
      id: fetchError
      waitForEnd: true
    }
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.lastError = String(fetchError.text || "Could not fetch WTI price").trim()
        root.label = "WTI —"
        root.tooltip = root.lastError
        return
      }
      try {
        var result = JSON.parse(String(fetchOutput.text || "{}"))
        root.label = String(result.text || "WTI —")
        root.tooltip = String(result.tooltip || "WTI crude-oil futures")
        root.lastError = ""
      } catch (error) {
        root.lastError = "Could not read price response"
        root.label = "WTI —"
        root.tooltip = root.lastError
      }
    }
  }

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.label
    tooltipText: root.tooltip
    // WidgetButton uses PlainText. Keep its interaction and tooltip handling,
    // but render the helper's colored percentage (or stale badge) ourselves.
    labelVisible: false
    implicitWidth: vertical ? barSize : Math.max(12, priceLabel.implicitWidth + scaledHorizontalMargin * 2)
    implicitHeight: vertical ? Math.max(12, priceLabel.implicitHeight + scaledVerticalPadding * 2) : barSize

    Text {
      id: priceLabel
      anchors.centerIn: parent
      text: root.label
      textFormat: Text.StyledText
      color: button.foreground
      font.family: button.fontFamily
      font.pixelSize: button.fontSize
      renderType: Text.NativeRendering
      rotation: button.textRotation
      horizontalAlignment: Text.AlignHCenter
      verticalAlignment: Text.AlignVCenter
    }

    // A click gives an immediate refresh without adding an unnecessary panel.
    onPressed: function(button) {
      if (button === Qt.LeftButton || button === Qt.MiddleButton) root.refresh()
    }
  }
}
