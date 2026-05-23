import pyvista as pv
from pathlib import Path


def vtk_to_stl(vtk_path, stl_path=None):
    vtk_path = Path(vtk_path)

    if stl_path is None:
        stl_path = vtk_path.with_suffix(".stl")
    else:
        stl_path = Path(stl_path)

    # VTK読み込み
    mesh = pv.read(vtk_path)

    # UnstructuredGridなどの場合は表面だけ抽出
    if not isinstance(mesh, pv.PolyData):
        mesh = mesh.extract_surface()

    # 重複点などを整理
    mesh = mesh.clean()

    # STLは基本的に三角形メッシュなので三角形化
    mesh = mesh.triangulate()

    # 法線を計算
    mesh = mesh.compute_normals(
        cell_normals=True,
        point_normals=False,
        consistent_normals=True,
        auto_orient_normals=True,
    )

    # STL保存
    mesh.save(stl_path)

    return str(stl_path)


if __name__ == "__main__":
    input_vtk = "/mount/moritadbjp/sharefilesjp/work/poseR6D/data/hood/SIM_geo_109_clusterID_8_crvCount_2_0218_1435_cd_0.025_md_0.041_08.vtk"
    output_stl = "/mount/moritadbjp/sharefilesjp/work/poseR6D/data/hood/SIM_geo_109_clusterID_8_crvCount_2_0218_1435_cd_0.025_md_0.041_08.stl"

    vtk_to_stl(input_vtk, output_stl)
    print(f"Saved: {output_stl}")