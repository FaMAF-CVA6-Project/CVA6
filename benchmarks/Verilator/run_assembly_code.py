#!/usr/bin/env python3
import os
import sys
import argparse
import subprocess
import datetime
import re
import shlex
import shutil

# ==============================================================================
# CONSTANTES DE OVERHEAD (cv64a6_imafdc_sv39_hpdcache_wb)
# ==============================================================================
OVERHEAD_CONSTANTS = {
    'x18': 40,   # Ciclos
    'x19': 17,   # Instrucciones
    'x20': 3,    # Misses I-Cache
    'x21': 0,    # Misses D-Cache
    'x22': 34,   # Accesos I-Cache 
    'x23': 9,    # Accesos D-Cache
    'x24': 0,    # Branches
    'x25': 0,    # Branch Mispredicts
    'x26': 0     # Tiempo (us)
}

# ==============================================================================
# CONFIGURACION
# ==============================================================================
METRICS_MAP = {
    'x18': 'Ciclos',               # s2
    'x19': 'Instrucciones',        # s3
    'x20': 'Misses I-Cache',       # s4
    'x21': 'Misses D-Cache',       # s5
    'x22': 'Accesos I-Cache',      # s6
    'x23': 'Accesos D-Cache',      # s7
    'x24': 'Branches',             # s8
    'x25': 'Branch Mispredicts',   # s9
    'x26': 'Tiempo (us)'           # s10
}

ORDERED_KEYS = ['x18', 'x19', 'x20', 'x21', 'x22', 'x23', 'x24', 'x25', 'x26']

def generate_and_show_codelist(binary_path):
    """
    Genera el archivo .list usando objdump y muestra la seccion de CODIGO filtrada.
    Devuelve la ruta del archivo limpio para posterior escritura.
    """
    if not os.path.exists(binary_path):
        print(f"[ERROR] No se encontro el binario para desmontar: {binary_path}")
        return None

    list_path = os.path.splitext(binary_path)[0] + ".list"
    clean_path = os.path.splitext(binary_path)[0] + "_clean.txt"
    
    cmd = f"riscv64-unknown-elf-objdump -d -S -l {binary_path}"
    
    print(f"\n[INFO] Generando codigo desensamblado en: {list_path}")
    try:
        with open(list_path, "w") as f:
            subprocess.run(shlex.split(cmd), stdout=f, check=True)
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {e}")
        return None
    except FileNotFoundError:
        print("[ERROR] No se encontro 'riscv64-unknown-elf-objdump'")
        return None

    # Visualizacion Filtrada
    print("\n" + "="*70)
    print("CODIGO DESENSAMBLADO")
    print("="*70 + "\n")

    start_pattern = "# PROGRAMA"
    end_pattern = "# SNAPSHOT FINAL Y CÁLCULO DE DIFERENCIAS"
    
    printing = False
    found_any = False

    try:
        with open(list_path, "r") as f:
            lines = f.readlines()
            
        with open(clean_path, "w") as f_clean:
            for line in lines:
                if end_pattern in line:
                    printing = False
                    break 

                if start_pattern in line:
                    printing = True
                    found_any = True
                    continue 

                if printing:
                    if re.search(r'#\s*-{5,}', line):
                        continue
                    
                    # Ignorar lineas que comienzan con rutas de archivo
                    if line.strip().startswith('/'):
                        continue

                    print(line, end='')
                    f_clean.write(line)

        if not found_any:
            print("[WARN] No se encontro la etiqueta '# PROGRAMA' en el .list\n")

    except Exception as e:
        print(f"[ERROR] {e}")
        return None
    
    print("=" * 70 + "\n")
    print(f"[INFO] Archivo limpio guardado en: {clean_path}")
    return clean_path

def main():
    # Configuracion de Directorios
    cva6_root = "/cva6"
    sim_dir = os.path.join(cva6_root, "verif/sim")
    setup_script = os.path.join(sim_dir, "setup-env.sh")
    
    # Definimos la carpeta de compilacion a borrar
    work_ver_path = os.path.join(cva6_root, "work-ver")

    # Forzar Recompilacion
    if os.path.exists(work_ver_path):
        try:
            shutil.rmtree(work_ver_path)
        except OSError as e:
            print(f"[WARN] {e}")

    # Parsear Argumentos
    parser = argparse.ArgumentParser(description="Ejecutar simulacion CVA6 y extraer metricas")
    parser.add_argument("target", help="Target de la arquitectura (ej: cv64a6_imafdc_sv39_hpdcache)")
    parser.add_argument("asm_file", help="Ruta al archivo .S o .asm (relativa o absoluta)")
    args = parser.parse_args()

    # Validar existencia del archivo ASM
    abs_asm_path = os.path.abspath(args.asm_file)
    if not os.path.exists(abs_asm_path):
        print(f"[ERROR] El archivo {abs_asm_path} no existe")
        sys.exit(1)

    rel_asm_path = os.path.relpath(abs_asm_path, sim_dir)
    test_name = os.path.splitext(os.path.basename(abs_asm_path))[0]
    
    # Preparar Entorno
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1" 
    env["DV_SIMULATORS"] = "veri-testharness"

    # Definicion de rutas de salida
    today = datetime.date.today().strftime("%Y-%m-%d")
    
    # Donde se guardan los logs de simulacion
    log_dir_prediction = os.path.join(sim_dir, f"out_{today}", "veri-testharness_sim")
    
    # Donde se guardan los binarios compilados
    binary_dir_compilation = os.path.join(sim_dir, f"out_{today}", "directed_tests")

    log_main = f"{test_name}.{args.target}.log"
    log_iss  = f"{test_name}.{args.target}.log.iss"
    
    # Limpieza de logs previos
    files_to_clean = [log_main, log_iss]
    for fname in files_to_clean:
        fpath = os.path.join(log_dir_prediction, fname)
        if os.path.exists(fpath):
            try:
                os.remove(fpath)
            except OSError:
                pass

    # Construir Comando
    py_cmd_list = [
        "python3", "cva6.py",
        "--target", args.target,
        f"--iss={env['DV_SIMULATORS']}",
        "--iss_yaml=cva6.yaml",
        "--asm_tests", rel_asm_path,
        "--linker=../../config/gen_from_riscv_config/linker/link.ld",
        f"--gcc_opts=-static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles -g ../tests/custom/common/syscalls.c ../tests/custom/common/crt.S -lgcc -I../tests/custom/env -I../tests/custom/common"
    ]

    py_cmd_str = shlex.join(py_cmd_list)
    final_shell_cmd = f"source {setup_script} && {py_cmd_str}"
    
    try:
        print(f"[INFO] Corriendo simulacion Verilator con '{test_name}.S'\n")
        subprocess.run(
            final_shell_cmd, 
            cwd=sim_dir, 
            check=True, 
            env=env, 
            stdout=subprocess.DEVNULL,
            shell=True,
            executable='/bin/bash'
        )
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {e.returncode}")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # GENERAR Y MOSTRAR CODIGO 
    # --------------------------------------------------------------------------
    binary_path = os.path.join(binary_dir_compilation, f"{test_name}.o")
    clean_path = generate_and_show_codelist(binary_path)

    # --------------------------------------------------------------------------
    # PARSEAR METRICAS
    # --------------------------------------------------------------------------
    log_path = os.path.join(log_dir_prediction, log_main)

    if not os.path.exists(log_path):
        print(f"[ERROR] Log de simulacion no encontrado: {log_path}")
        sys.exit(1)

    final_values = {}
    try:
        with open(log_path, 'r') as f:
            for line in f:
                match = re.search(r'x\s*(\d+)\s+(0x[0-9a-fA-F]+)', line)
                if match:
                    reg_key = f"x{match.group(1)}"
                    if reg_key in METRICS_MAP:
                        final_values[reg_key] = int(match.group(2), 16)
    except Exception as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    # --------------------------------------------------------------------------
    # CALCULOS E IMPRESION DE TABLA
    # --------------------------------------------------------------------------
    print("[INFO] Extrayendo estadisticas\n")

    clean_official = []
    clean_corrected = []

    # Pre-calculo IPC Corrected
    raw_inst = final_values.get('x19', 0)
    ovh_inst = OVERHEAD_CONSTANTS.get('x19', 0)
    net_inst = max(0, raw_inst - ovh_inst)

    raw_cycles = final_values.get('x18', 1)
    ovh_cycles = OVERHEAD_CONSTANTS.get('x18', 0)
    net_cycles = max(1, raw_cycles - ovh_cycles)

    ipc_official = raw_inst / raw_cycles if raw_cycles > 0 else 0
    ipc_corrected = net_inst / net_cycles

    output_buffer = []
    output_buffer.append("=" * 70)
    output_buffer.append("TABLA DE RESULTADOS")
    output_buffer.append("=" * 70)
    output_buffer.append(f"{'METRICA':<25} | {'OFICIAL':>15} | {'NETO':>15}")
    output_buffer.append("=" * 70)

    # Iterar Metricas
    for key in ORDERED_KEYS:
        metric_name = METRICS_MAP[key]
        val_official = final_values.get(key, 0)
        overhead = OVERHEAD_CONSTANTS.get(key, 0)
        
        # Calcular Neto
        val_corrected = max(0, val_official - overhead)

        # Formateo
        clean_official.append(val_official)
        clean_corrected.append(val_corrected)
        
        output_buffer.append(f"{metric_name:<25} | {val_official:>15} | {val_corrected:>15}")

    # Imprimir IPC
    output_buffer.append(f"{'IPC':<25} | {ipc_official:>15.4f} | {ipc_corrected:>15.4f}")
    
    # Agregar IPC a las listas limpias
    clean_official.append(round(ipc_official, 4))
    clean_corrected.append(round(ipc_corrected, 4))

    output_buffer.append("=" * 70)
    output_buffer.append(f"\nClean result (OFICIAL):  {clean_official}")
    output_buffer.append(f"Clean result (NETO):     {clean_corrected}\n")

    # Mostrar todo en la consola
    for line in output_buffer:
        print(line)

    # Guardar exactamente el mismo bloque en el archivo _clean.txt
    if clean_path and os.path.exists(clean_path):
        try:
            with open(clean_path, "a") as f_clean:
                f_clean.write("\n\n")
                for line in output_buffer:
                    f_clean.write(line + "\n")
            print(f"[INFO] Metricas consolidadas exitosamente en: {clean_path}")
        except Exception as e:
            print(f"[WARN] No se pudieron guardar las metricas en el archivo: {e}")

if __name__ == "__main__":
    main()