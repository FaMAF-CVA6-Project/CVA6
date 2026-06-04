#!/usr/bin/env python3
import sys
import os
import subprocess
import re
import argparse

# ==============================================================================
# CONFIGURACION GLOBAL
# ==============================================================================
GEM5_ROOT = os.getcwd()
GCC_CMD = "riscv64-unknown-elf-gcc"
OBJDUMP_CMD = "riscv64-unknown-elf-objdump"
GEM5_BIN = "./build/RISCV/gem5.opt"
M5_INCLUDE = os.path.join(GEM5_ROOT, "include")
M5_OP_ASM = os.path.join(GEM5_ROOT, "util/m5/src/abi/riscv/m5op.S")

# ==============================================================================
# CONSTANTES DE OVERHEAD (Configuracion CVA6)
# ==============================================================================
OVERHEAD_CONSTANTS = {
    "numCycles":        0,
    "numInsts":         0,
    "icache_miss":      0,
    "dcache_miss":      0,
    "icache_access":    0,
    "dcache_access":    0,
    "branch_pred":      0,
    "branch_miss":      2,
    "simSeconds":       0.0 # En segundos
}

# ==============================================================================
# MAPA DE METRICAS
# ==============================================================================
METRICS_MAP = {
    "numCycles":         r"cores\.core\.numCycles",
    "numInsts":          r"cores\.core\.commitStats0\.numInsts\s",
    "icache_miss":       r"l1icaches\.overallMisses::total",
    "dcache_miss_read":  r"l1dcaches\.ReadReq.misses::total",
    "dcache_miss_write": r"l1dcaches\.WriteReq.misses::total",
    "icache_access":     r"l1icaches\.overallAccesses::total",
    "dcache_access":     r"l1dcaches\.overallAccesses::total",
    "bp_look_d_cond":    r"branchPred\.btb\.lookups::DirectCond\b",
    "bp_look_d_uncond":  r"branchPred\.btb\.lookups::DirectUncond\b",
    "bp_look_i_uncond":  r"branchPred\.btb\.lookups::IndirectUncond\b",
    "btb_misp_d_cond":   r"branchPred\.btb\.mispredict::DirectCond\b",
    "btb_misp_d_uncond": r"branchPred\.btb\.mispredict::DirectUncond\b",
    "btb_misp_i_uncond": r"branchPred\.btb\.mispredict::IndirectUncond\b",
    "bp_cond_incorrect": r"branchPred\.condIncorrect\b",
    "simSeconds":        r"simSeconds",
    "ipc":               r"cores\.core\.ipc"
}

PRETTY_NAMES = {
    "numCycles": "Ciclos",
    "numInsts": "Instrucciones",
    "icache_miss": "Misses I-Cache",
    "dcache_miss": "Misses D-Cache",
    "icache_access": "Accesos I-Cache",
    "dcache_access": "Accesos D-Cache",
    "branch_pred": "Branches",
    "branch_miss": "Branch Miss + Unpred",
    "simSeconds": "Tiempo (us)",
    "ipc": "IPC"
}

def compile_asm(asm_file):
    base_name = os.path.splitext(asm_file)[0]
    bin_file = base_name
    print(f"[INFO] Compilando {asm_file} -> {bin_file}")
    cmd = [
        GCC_CMD, "-static", "-mcmodel=medany", "-fvisibility=hidden",
        "-nostdlib", "-nostartfiles", "-lgcc",
        "-march=rv64gc_zba_zbb_zbs_zbc_zbkb_zbkx_zkne_zknd_zknh", "-mabi=lp64d",
        f"-I{M5_INCLUDE}", asm_file, M5_OP_ASM, "-o", bin_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[ERROR]", result.stderr)
        sys.exit(1)
    return bin_file

def run_gem5(config_file, bin_file, no_trace, program_name):
    out_dir = "resultados"
    os.makedirs(out_dir, exist_ok=True)

    # Limpiar stats anteriores para evitar confusion
    stats_path = os.path.join(out_dir, "stats.txt")
    if os.path.exists(stats_path):
        os.remove(stats_path)

    # Inicializar comando base de gem5
    cmd = [GEM5_BIN]

    # Si NO se activa el flag '--no-trace', agregamos las banderas de depuracion solicitadas
    if not no_trace:
        trace_file = f"{program_name}_trace.txt"
        print(f"[INFO] Habilitando trazas detalladas de depuracion en: {os.path.join(out_dir, trace_file)}")
        cmd.extend([
            "--debug-flags=Minor,MinorTrace,MinorTiming,CacheAll,ExecAll,Fetch,Decode,IEW,Commit,LSQ,Scoreboard,Writeback",
            f"--debug-file={trace_file}"
        ])

    # Agregar directorio de salida e inputs finales
    cmd.extend(["-d", out_dir, config_file, bin_file])

    print(f"[INFO] Corriendo simulacion gem5 usando '{config_file}'")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[ERROR]", result.stderr)
        sys.exit(1)
    return stats_path

def generate_and_show_codelist(bin_file, program_name):
    out_dir = "resultados"
    os.makedirs(out_dir, exist_ok=True)
    list_file = os.path.join(out_dir, f"{program_name}.list")
    clean_file = os.path.join(out_dir, f"{program_name}_clean.txt")

    print(f"[INFO] Generando codigo desensamblado en: {list_file}")

    cmd = [OBJDUMP_CMD, "-d", "-S", "-l", bin_file]

    try:
        with open(list_file, "w") as f:
            subprocess.run(cmd, stdout=f, check=True)
    except subprocess.CalledProcessError as e:
        print("[ERROR]", e)
        sys.exit(1)

    print("\n" + "="*70)
    print(f"CODIGO DESENSAMBLADO")
    print("="*70)

    try:
        with open(list_file, "r") as f, open(clean_file, "w") as f_clean:
            for line in f:
                print(line, end='')
                f_clean.write(line)
                if "jal" in line and "<m5_dump_stats>" in line:
                    break
    except FileNotFoundError:
        print(f"[WARN] No se pudo leer el archivo generado {list_file}")
        return None

    print("\n" + "="*70 + "\n")
    print(f"[INFO] Archivo limpio guardado en: {clean_file}")
    return clean_file

def parse_stats(stats_path):
    print("[INFO] Extrayendo estadisticas\n")
    results = {key: 0.0 for key in METRICS_MAP}

    block_count = 0
    in_target_block = False

    try:
        with open(stats_path, 'r') as f:
            for line in f:
                if "Begin Simulation Statistics" in line:
                    block_count += 1
                    # Asumimos que el ROI esta en el primer bloque de stats
                    if block_count == 1:
                        in_target_block = True
                    else:
                        in_target_block = False

                if in_target_block:
                    for key, regex in METRICS_MAP.items():
                        if re.search(regex, line):
                            parts = line.split()
                            if len(parts) >= 2:
                                try:
                                    val = float(parts[1])
                                    results[key] = val
                                except ValueError:
                                    pass
    except FileNotFoundError:
        print("[ERROR] No se encontro stats.txt")
        sys.exit(1)

    # Consolidar misses de D-Cache (lectura + escritura)
    total_dcache_miss = (results.get("dcache_miss_read", 0) +
                         results.get("dcache_miss_write", 0))
    results["dcache_miss"] = total_dcache_miss

    # Total Saltos Logicos
    total_branches = (results.get("bp_look_d_cond", 0) +
                      results.get("bp_look_d_uncond", 0) +
                      results.get("bp_look_i_uncond", 0))
    results["branch_pred"] = total_branches

    # Total mispredicts
    total_failures = (
        results.get("bp_cond_incorrect", 0) +
        results.get("btb_misp_d_uncond", 0) +
        results.get("btb_misp_i_uncond", 0)
    )
    results["branch_miss"] = total_failures

    return results

def print_table(results, clean_file=None):
    # Buffer temporal para guardar el texto de salida
    output_buffer = []

    output_buffer.append("="*70)
    output_buffer.append(f"TABLA DE RESULTADOS")
    output_buffer.append("="*70)
    output_buffer.append(f"{'METRICA':<25} | {'OFICIAL':>15} | {'NETO':>15}")
    output_buffer.append("="*70)

    keys_order = ["numCycles", "numInsts","icache_miss", "dcache_miss",
                  "icache_access", "dcache_access","branch_pred",
                  "branch_miss", "simSeconds", "ipc"]

    clean_array_official = []
    clean_array_corrected = []

    # Pre-calculo para IPC corregido
    raw_insts = results.get("numInsts", 0)
    ovh_insts = OVERHEAD_CONSTANTS.get("numInsts", 0)
    net_insts = max(0, raw_insts - ovh_insts)

    raw_cycles = results.get("numCycles", 1) # Evitar div por cero
    ovh_cycles = OVERHEAD_CONSTANTS.get("numCycles", 0)
    net_cycles = max(1, raw_cycles - ovh_cycles) # Evitar div por cero

    corrected_ipc = net_insts / net_cycles
    for key in keys_order:
        val_official = results.get(key, 0)
        label = PRETTY_NAMES.get(key, key)
        overhead = OVERHEAD_CONSTANTS.get(key, 0)

        if key == "ipc":
            val_corrected = corrected_ipc
        else:
            val_corrected = max(0, val_official - overhead)
        if key == "simSeconds":
            val_off_us = val_official * 1_000_000
            val_cor_us = val_corrected * 1_000_000

            fmt_off = f"{int(val_off_us)}"
            fmt_cor = f"{int(val_cor_us)}"

            clean_array_official.append(round(val_off_us))
            clean_array_corrected.append(round(val_cor_us))

        elif key == "ipc":
            fmt_off = f"{val_official:.4f}"
            fmt_cor = f"{val_corrected:.4f}"

            clean_array_official.append(round(val_official, 4))
            clean_array_corrected.append(round(val_corrected, 4))

        else:
            fmt_off = f"{int(val_official)}"
            fmt_cor = f"{int(val_corrected)}"

            clean_array_official.append(int(val_official))
            clean_array_corrected.append(int(val_corrected))

        output_buffer.append(f"{label:<25} | {fmt_off:>15} | {fmt_cor:>15}")

    output_buffer.append("="*70)
    output_buffer.append(f"\nClean result (OFICIAL):  {clean_array_official}")
    output_buffer.append(f"Clean result (NETO):     {clean_array_corrected}\n")

    # Imprimir tabla y listas en consola
    for line in output_buffer:
        print(line)

    # Adjuntar la tabla y listas al final del archivo code_clean.txt
    if clean_file and os.path.exists(clean_file):
        try:
            with open(clean_file, "a") as f_clean:
                f_clean.write("\n\n")
                for line in output_buffer:
                    f_clean.write(line + "\n")
            print(f"[INFO] Metricas consolidadas exitosamente en: {clean_file}")
        except Exception as e:
            print(f"[WARN] No se pudieron guardar las metricas en el archivo: {e}")
            
if __name__ == "__main__":
    # Configuracion de argumentos mediante argparse
    parser = argparse.ArgumentParser(description="Ejecutar simulacion gem5 en RISC-V y consolidar reportes.")
    parser.add_argument("config_file", help="Ruta al archivo de configuracion de gem5 (.py)")
    parser.add_argument("asm_file", help="Ruta al archivo de codigo assembly (.S o .asm)")
    parser.add_argument("--no-trace", action="store_true", help="Desactiva la recopilacion de trazas detalladas de depuracion")

    args = parser.parse_args()

    config_file = args.config_file
    asm_file = args.asm_file

    if not os.path.exists(config_file):
        print(f"[ERROR] El archivo de configuracion '{config_file}' no existe")
        sys.exit(1)
    if not os.path.exists(asm_file):
        print(f"[ERROR] El archivo de programa '{asm_file}' no existe")
        sys.exit(1)

    # Obtener el nombre base del programa (ej: "mi_programa" desde "dir/mi_programa.S")
    program_name = os.path.splitext(os.path.basename(asm_file))[0]

    binary = compile_asm(asm_file)
    stats_file = run_gem5(config_file, binary, args.no_trace, program_name)

    clean_file = generate_and_show_codelist(binary, program_name)

    metrics = parse_stats(stats_file)
    print_table(metrics, clean_file)