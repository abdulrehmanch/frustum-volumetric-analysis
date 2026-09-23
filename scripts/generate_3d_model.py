"""
Generate 3D Model and Visualizations for South Contour Area.
Demonstrates the 3D terrain morphology, internal contour slices, and tub/dam profile.
"""

import os
import geopandas as gpd
import numpy as np
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.interpolate import griddata
from scipy.spatial import Delaunay
from shapely.geometry import Polygon
from shapely import contains_xy
import plotly.graph_objects as go

def main():
    base_dir = "/Users/abdulrehman/Downloads/Clip_Contour_North/frustum_volumetric_analysis"
    shp_path = os.path.join(base_dir, "south", "input", "Contours.shp")
    out_dir = os.path.join(base_dir, "south", "output")
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Loading {shp_path}...")
    gdf = gpd.read_file(shp_path).to_crs(epsg=32643)
    
    boundary_geom = gdf[gdf['ELEVATION'] == 0].geometry.iloc[0]
    bound_poly = Polygon(boundary_geom.coords)
    contours_gdf = gdf[gdf['ELEVATION'] > 0]
    
    # Extract all contour points (X, Y, Z)
    pts = []
    contour_lines_3d = []
    
    for idx, row in contours_gdf.iterrows():
        geom = row.geometry
        elev = row['ELEVATION']
        if geom.geom_type == 'LineString':
            lines = [geom]
        elif geom.geom_type == 'MultiLineString':
            lines = list(geom.geoms)
        else:
            continue
            
        for line in lines:
            c = list(line.coords)
            contour_lines_3d.append((np.array(c)[:, 0], np.array(c)[:, 1], np.full(len(c), elev), elev))
            for pt in c:
                pts.append((pt[0], pt[1], elev))
                
    pts = np.array(pts)
    print(f"Total contour 3D survey vertices: {len(pts)}")
    
    # Center coordinates relative to local origin for numerical precision & cleaner plots
    x_ref = np.min(pts[:, 0])
    y_ref = np.min(pts[:, 1])
    z_min = np.min(pts[:, 2])
    z_max = np.max(pts[:, 2])
    
    print(f"Local reference origin: Easting={x_ref:.1f}, Northing={y_ref:.1f}")
    print(f"Elevation span: {z_min:.1f} m to {z_max:.1f} m (Delta H = {z_max - z_min:.1f} m)")
    
    # -------------------------------------------------------------
    # 1. High-Resolution Delaunay TIN Mesh
    # -------------------------------------------------------------
    print("Building Constrained Delaunay 3D Mesh...")
    tri = Delaunay(pts[:, :2])
    triangles = tri.simplices
    
    # Filter triangles whose centroids lie inside the boundary polygon
    centroids_x = pts[triangles, 0].mean(axis=1)
    centroids_y = pts[triangles, 1].mean(axis=1)
    inside_mask = contains_xy(bound_poly, centroids_x, centroids_y)
    valid_triangles = triangles[inside_mask]
    print(f"Retained {len(valid_triangles)} valid 3D triangles within boundary corridor.")

    # -------------------------------------------------------------
    # 2. Interactive 3D HTML Model with Plotly
    # -------------------------------------------------------------
    print("Generating interactive 3D HTML model...")
    fig_plotly = go.Figure()
    
    # A. 3D Shaded Surface Mesh
    fig_plotly.add_trace(go.Mesh3d(
        x=pts[:, 0],
        y=pts[:, 1],
        z=pts[:, 2],
        i=valid_triangles[:, 0],
        j=valid_triangles[:, 1],
        k=valid_triangles[:, 2],
        intensity=pts[:, 2],
        colorscale='Viridis',
        colorbar=dict(title='Elevation (m)', thickness=15, len=0.7),
        opacity=0.92,
        name='Terrain Surface (TIN)',
        hoverinfo='x+y+z'
    ))
    
    # B. Tracing 3D Contour Lines on the model
    # Tracing key contours to highlight internal contours
    for x_c, y_c, z_c, elev in contour_lines_3d:
        fig_plotly.add_trace(go.Scatter3d(
            x=x_c,
            y=y_c,
            z=z_c,
            mode='lines',
            line=dict(color='white' if elev == 165.5 or elev == 157.0 else 'black', width=3 if elev in [157.0, 161.0, 165.5] else 1.5),
            hovertext=f"Contour: {elev:.1f} m",
            hoverinfo='text',
            showlegend=False
        ))
        
    # C. Outer Boundary Wireframe
    bnd_coords = np.array(boundary_geom.coords)
    # Project boundary onto z_min for a baseline reference
    fig_plotly.add_trace(go.Scatter3d(
        x=bnd_coords[:, 0],
        y=bnd_coords[:, 1],
        z=np.full(len(bnd_coords), z_min),
        mode='lines',
        line=dict(color='red', width=4, dash='dash'),
        name='Boundary Base (157.0 m)',
        hoverinfo='name'
    ))
    
    fig_plotly.update_layout(
        title=dict(
            text='<b>Interactive 3D Terrain Model: South Contour Area</b><br><sup>Tub / Dam Morphology with Multi-Layer Internal Contours</sup>',
            x=0.5
        ),
        scene=dict(
            xaxis_title='Easting (m)',
            yaxis_title='Northing (m)',
            zaxis_title='Elevation (m)',
            aspectmode='manual',
            aspectratio=dict(x=1, y=2, z=0.6), # Vertical exaggeration for clear relief
            camera=dict(
                eye=dict(x=1.6, y=-1.6, z=1.2)
            )
        ),
        width=1100,
        height=800,
        margin=dict(r=20, l=20, b=20, t=60)
    )
    
    html_output = os.path.join(out_dir, "south_3d_terrain_model.html")
    fig_plotly.write_html(html_output)
    print(f"Saved interactive 3D model: {html_output}")

    # -------------------------------------------------------------
    # 3. Static High-Resolution Multi-Perspective 3D Renders (PNG)
    # -------------------------------------------------------------
    print("Rendering static 3D perspective views...")
    fig = plt.figure(figsize=(20, 16))
    
    # Relative coordinates for matplotlib 3D
    x_rel = pts[:, 0] - x_ref
    y_rel = pts[:, 1] - y_ref
    z_rel = pts[:, 2]
    
    # Views:
    # 1. Isometric Perspective View
    # 2. Side Elevation View (Looking West-to-East)
    # 3. Longitudinal Profile (Looking South-to-North)
    # 4. Top-Down Planimetric View with 3D Contour Ribbons
    views = [
        (1, "1. Isometric Perspective View (South-East)", 28, -60),
        (2, "2. Side Cross-Profile (Tub Slope View)", 10, -95),
        (3, "3. Front Crest-to-Toe View (Looking North)", 15, -170),
        (4, "4. High-Angle Angled View with Slices", 55, -45)
    ]
    
    for idx, title, elev_angle, azim_angle in views:
        ax = fig.add_subplot(2, 2, idx, projection='3d')
        
        # Plot Triangulated Surface
        surf = ax.plot_trisurf(
            x_rel, y_rel, z_rel,
            triangles=valid_triangles,
            cmap='terrain',
            edgecolor='none',
            alpha=0.85,
            antialiased=True
        )
        
        # Overlay 3D contour lines
        for x_c, y_c, z_c, el in contour_lines_3d:
            c_color = 'red' if el == 165.5 else ('blue' if el == 157.0 else 'black')
            c_lw = 1.8 if el in [157.0, 161.0, 165.5] else 0.8
            ax.plot(x_c - x_ref, y_c - y_ref, z_c, color=c_color, linewidth=c_lw, alpha=0.9)
            
        ax.view_init(elev=elev_angle, azim=azim_angle)
        ax.set_title(title, fontsize=13, weight='bold', pad=10)
        ax.set_xlabel('Relative Easting (m)', fontsize=9)
        ax.set_ylabel('Relative Northing (m)', fontsize=9)
        ax.set_zlabel('Elevation (m)', fontsize=9)
        ax.set_zlim(155, 167)
        
    plt.suptitle("South Area: 3D Topographic Morphology & Multi-Layer Contours\n(Top Crest: 165.5 m | Base Toe: 157.0 m | Boundary Corridor)", fontsize=16, weight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    
    png_output = os.path.join(out_dir, "south_3d_perspectives.png")
    plt.savefig(png_output, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved 3D perspectives plot: {png_output}")

    # -------------------------------------------------------------
    # 4. Longitudinal Cross-Section Profile (Tub Cross-Section)
    # -------------------------------------------------------------
    print("Generating longitudinal cross-section slice diagram...")
    # Sample a profile line from South (165.5 crest) to North (157.0 base)
    y_profile = np.linspace(np.min(pts[:, 1]), np.max(pts[:, 1]), 300)
    # Take center Easting line
    x_center = np.median(pts[:, 0])
    
    # Interpolate along this center line
    z_profile = griddata(pts[:, :2], pts[:, 2], (np.full_like(y_profile, x_center), y_profile), method='linear')
    
    # Filter valid
    valid_idx = ~np.isnan(z_profile)
    dist_profile = y_profile[valid_idx] - y_profile[valid_idx][0]
    z_profile_valid = z_profile[valid_idx]
    
    plt.figure(figsize=(12, 6))
    plt.plot(dist_profile, z_profile_valid, color='#023e8a', linewidth=2.5, label='Terrain Bed Line Z(y)')
    plt.fill_between(dist_profile, 157.0, z_profile_valid, color='#90e0ef', alpha=0.6, label='Material Body / Internal Slices')
    
    # Draw internal contour horizontal lines matching the user's sketch!
    for el in np.arange(157.5, 166.0, 1.0):
        plt.axhline(el, color='black', linestyle='--', linewidth=0.9, alpha=0.7)
        plt.text(dist_profile[-1] * 0.02, el + 0.1, f"Internal Contour {el:.1f} m", fontsize=8, color='#333333', weight='bold')
        
    plt.title("Longitudinal Terrain Profile: Embankment Slope & Internal Contour Slices", fontsize=13, weight='bold')
    plt.xlabel("Distance Along Corridor from South Crest to North Toe (m)", fontsize=10)
    plt.ylabel("Elevation (m)", fontsize=10)
    plt.grid(True, linestyle=':', alpha=0.6)
    plt.ylim(156.5, 166.5)
    plt.legend(loc='upper right')
    
    profile_output = os.path.join(out_dir, "south_longitudinal_profile.png")
    plt.savefig(profile_output, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"Saved cross-section profile: {profile_output}")
    print("\nAll 3D models and visualization assets successfully generated!")

if __name__ == '__main__':
    main()
