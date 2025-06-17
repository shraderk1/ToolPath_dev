import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, QFileDialog, QMessageBox, QStatusBar, QLabel,
    QListWidget, QAbstractItemView, QHBoxLayout, QDialog, QPushButton, QSlider
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
import os
import pyqtgraph.opengl as gl
import pyqtgraph as pg
import numpy as np

class GCodeEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("3D Printing Toolpath (G-code) Editor")
        self.setGeometry(100, 100, 650, 350)
        self.gcode_file_path = None
        self.cleaned_gcode = None
        self.layer_indices = []
        self.layer_labels = []
        self.selected_layers = set()
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)
        main_layout.setAlignment(Qt.AlignCenter)

        self.info_label = QLabel("No G-code file selected.")
        self.info_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(10)
        self.info_label.setFont(font)
        main_layout.addWidget(self.info_label)

        btn_layout = QHBoxLayout()
        self.open_button = QPushButton("Select G-code File")
        self.open_button.setMinimumHeight(32)
        self.open_button.setFont(QFont('Arial', 11))
        self.open_button.clicked.connect(self.open_gcode_file)
        btn_layout.addWidget(self.open_button)

        self.save_button = QPushButton("Save As")
        self.save_button.setMinimumHeight(32)
        self.save_button.setFont(QFont('Arial', 11))
        self.save_button.clicked.connect(self.save_gcode_file)
        self.save_button.setEnabled(False)
        btn_layout.addWidget(self.save_button)

        self.layer_button = QPushButton("Select Layers")
        self.layer_button.setMinimumHeight(32)
        self.layer_button.setFont(QFont('Arial', 11))
        self.layer_button.clicked.connect(self.show_layer_selector)
        self.layer_button.setEnabled(False)
        btn_layout.addWidget(self.layer_button)

        self.view_layer_button = QPushButton("View Layer 3D")
        self.view_layer_button.setMinimumHeight(32)
        self.view_layer_button.setFont(QFont('Arial', 11))
        self.view_layer_button.clicked.connect(self.view_selected_layer)
        self.view_layer_button.setEnabled(False)
        btn_layout.addWidget(self.view_layer_button)

        main_layout.addLayout(btn_layout)

        # Placeholder for 3D G-code viewer
        # TODO: Add 3D viewer widget here in the future

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def open_gcode_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select G-code File", "", "G-code Files (*.gcode *.nc *.txt);;All Files (*)")
        if file_path:
            self.gcode_file_path = file_path
            filename = os.path.basename(file_path)
            self.info_label.setText(f"Selected: {filename}")
            self.save_button.setEnabled(True)
            self.status_bar.showMessage(f"Selected: {filename}")
            try:
                with open(file_path, 'r') as file:
                    gcode = file.readlines()
                self.cleaned_gcode = self.remove_all_thumbnails(gcode)
                self.parse_layers(self.cleaned_gcode)
                self.layer_button.setEnabled(True if self.layer_indices else False)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to read file: {e}")
                self.cleaned_gcode = None
                self.layer_indices = []
                self.layer_labels = []
                self.layer_button.setEnabled(False)
        else:
            self.status_bar.showMessage("No file selected.")

    def parse_layers(self, lines):
        self.layer_indices = []
        self.layer_labels = []
        for i, line in enumerate(lines):
            if line.strip() == ';LAYER_CHANGE':
                label = f"Layer {len(self.layer_indices)}"
                self.layer_indices.append(i)
                self.layer_labels.append(label)

    def show_layer_selector(self):
        if not self.layer_labels:
            QMessageBox.warning(self, "Warning", "No layers found in the G-code file.")
            return
        dlg = LayerSelectorDialog(self.layer_labels, self.selected_layers, self)
        if dlg.exec_():
            self.selected_layers = dlg.get_selected_layers()
            if not self.selected_layers:
                QMessageBox.warning(self, "Warning", "No layers selected.")
                self.view_layer_button.setEnabled(False)
            elif len(self.selected_layers) == 1:
                self.view_layer_button.setEnabled(True)
                self.status_bar.showMessage(f"Selected layer: {list(self.selected_layers)[0]}")
            else:
                self.view_layer_button.setEnabled(False)
                self.status_bar.showMessage(f"Selected layers: {sorted(self.selected_layers)}")

    def remove_all_thumbnails(self, lines):
        cleaned = []
        skip = False
        for line in lines:
            if 'thumbnail_QOI begin' in line or 'thumbnail begin' in line:
                skip = True
                continue
            if 'thumbnail_QOI end' in line or 'thumbnail end' in line:
                skip = False
                continue
            if not skip:
                cleaned.append(line)
        return cleaned

    def save_gcode_file(self):
        if not self.gcode_file_path or self.cleaned_gcode is None:
            QMessageBox.warning(self, "Warning", "No G-code
            return
        if not self.selected_layers:
            QMessageBox.warning(self, "Warning", "No layers selected for editing.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Save G-code File As", "", "G-code Files (*.gcode *.nc *.txt);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w') as file:
                    file.writelines(self.cleaned_gcode)
                self.status_bar.showMessage(f"Saved: {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save file: {e}")
        else:
            self.status_bar.showMessage("Save operation cancelled.")

    def view_selected_layer(self):
        if len(self.selected_layers) != 1:
            QMessageBox.warning(self, "Warning", "Please select exactly one layer to view.")
            return
        idx = list(self.selected_layers)[0]
        start = self.layer_indices[idx]
        end = self.layer_indices[idx+1] if idx+1 < len(self.layer_indices) else len(self.cleaned_gcode)
        layer_lines = self.cleaned_gcode[start:end]
        dlg = Layer3DViewerDialog(layer_lines, self)
        dlg.exec_()

class LayerSelectorDialog(QDialog):
    def __init__(self, layer_labels, selected_layers, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Layers")
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.MultiSelection)
        for idx, label in enumerate(layer_labels):
            self.list_widget.addItem(label)
            if idx in selected_layers:
                self.list_widget.item(idx).setSelected(True)
        layout.addWidget(self.list_widget)
        btn_box = QHBoxLayout()
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_box.addWidget(ok_btn)
        btn_box.addWidget(cancel_btn)
        layout.addLayout(btn_box)
    def get_selected_layers(self):
        return set([i.row() for i in self.list_widget.selectedIndexes()])

class Layer3DViewerDialog(QDialog):
    def __init__(self, layer_lines, parent=None):
        super().__init__(parent)
        self.setWindowTitle("3D Layer Viewer")
        self.setMinimumSize(900, 700)
        self.setWindowState(self.windowState() | Qt.WindowMaximized)
        self.layer_lines = layer_lines
        self.moves = self.parse_moves(layer_lines)
        self.current_index = len(self.moves) if self.moves else 0
        layout = QVBoxLayout(self)
        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setBackgroundColor('w')
        layout.addWidget(self.gl_widget, stretch=1)
        slider_layout = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(len(self.moves) if self.moves else 1)
        self.slider.setValue(self.current_index)
        self.slider.valueChanged.connect(self.update_plot)
        slider_layout.addWidget(self.slider)
        self.status_label = QLabel()
        slider_layout.addWidget(self.status_label)
        layout.addLayout(slider_layout)
        self.update_plot()
    def parse_moves(self, lines):
        moves = []
        x = y = z = e = None
        last_x = last_y = last_z = last_e = None
        current_type = None
        for line in lines:
            line = line.strip()
            if not line or line.startswith('M'):
                continue
            if line.startswith(';TYPE:External perimeter'):
                current_type = 'external_perimeter'
                continue
            elif line.startswith(';TYPE:Perimeter'):
                current_type = 'perimeter'
                continue
            elif line.startswith(';TYPE:Travel'):
                current_type = 'travel'
                continue
            elif line.startswith(';TYPE:'):
                current_type = None
                continue
            if line.startswith('G0') or line.startswith('G1') or line.startswith('G01'):
                parts = line.split()
                for part in parts:
                    if part.startswith('X'):
                        x = float(part[1:])
                    elif part.startswith('Y'):
                        y = float(part[1:])
                    elif part.startswith('Z'):
                        z = float(part[1:])
                    elif part.startswith('E'):
                        try:
                            e = float(part[1:])
                        except ValueError:
                            pass
                if x is not None and y is not None:
                    moves.append({'x': x, 'y': y, 'z': z if z is not None else (last_z if last_z is not None else 0), 'e': e if e is not None else (last_e if last_e is not None else 0), 'type': current_type})
                    last_x, last_y, last_z, last_e = x, y, z if z is not None else last_z, e if e is not None else last_e
            elif line.startswith('G2') or line.startswith('G3'):
                parts = line.split()
                for part in parts:
                    if part.startswith('X'):
                        x = float(part[1:])
                    elif part.startswith('Y'):
                        y = float(part[1:])
                    elif part.startswith('Z'):
                        z = float(part[1:])
                    elif part.startswith('E'):
                        try:
                            e = float(part[1:])
                        except ValueError:
                            pass
                if x is not None and y is not None:
                    moves.append({'x': x, 'y': y, 'z': z if z is not None else (last_z if last_z is not None else 0), 'e': e if e is not None else (last_e if last_e is not None else 0), 'type': current_type})
                    last_x, last_y, last_z, last_e = x, y, z if z is not None else last_z, e if e is not None else last_e
        print(f"Diagnostic: Parsed {len(moves)} moves from G-code.")
        return moves

    def update_plot(self):
        self.gl_widget.clear()
        idx = self.slider.value()
        if not self.moves or idx < 2:
            self.status_label.setText("Not enough moves to display.")
            return
        pts = np.array([[m['x'], m['y'], m['z']] for m in self.moves[:idx]])
        # Add axes/grid for reference
        grid = gl.GLGridItem()
        grid.setSize(x=200, y=200)
        grid.setSpacing(x=10, y=10)
        self.gl_widget.addItem(grid)
        grid.translate((pts[:,0].min()+pts[:,0].max())/2, (pts[:,1].min()+pts[:,1].max())/2, 0)
        # Draw toolpath segments by type
        for i in range(1, idx):
            seg = np.array([pts[i-1], pts[i]])
            move_type = self.moves[i]['type']
            color = (0,0,1,1)  # Default: blue (perimeter)
            width = 3
            antialias = True
            if move_type == 'external_perimeter':
                color = (0.5,0,0.5,1)  # Purple
            elif move_type == 'travel':
                color = (0,1,0,1)  # Green
                width = 2
                antialias = False
            plt = gl.GLLinePlotItem(pos=seg, color=color, width=width, antialias=antialias, mode='lines')
            if move_type == 'travel':
                plt.setGLOptions('translucent')
            self.gl_widget.addItem(plt)
        # Draw extruder position as a large opaque red dot (above lines)
        last = pts[idx-1]
        scatter = gl.GLScatterPlotItem(pos=np.array([last]), color=(1,0,0,1), size=40, pxMode=True)
        self.gl_widget.addItem(scatter)
        self.status_label.setText(f"Showing {idx} moves / {len(self.moves)}")
        # Set camera to fit the data
        x_range = np.ptp(pts[:,0])
        y_range = np.ptp(pts[:,1])
        max_range = max(x_range, y_range, 100)
        center_coords = [(pts[:,0].min()+pts[:,0].max())/2, (pts[:,1].min()+pts[:,1].max())/2, (pts[:,2].min()+pts[:,2].max())/2]
        center = pg.Vector(center_coords[0], center_coords[1], center_coords[2])
        self.gl_widget.setCameraPosition(pos=center, distance=max_range, elevation=90, azimuth=0)
        self.gl_widget.setBackgroundColor('w')

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = GCodeEditor()
    window.show()
    sys.exit(app.exec_())
