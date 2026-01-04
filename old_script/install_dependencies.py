#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
INSTALLAZIONE DIPENDENZE - Installa tutto il necessario per gestire QCOW2
"""

import os
import sys
import subprocess
import platform
import urllib.request
import zipfile
from pathlib import Path

def check_python_version():
    """Verifica versione Python."""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7+ richiesto")
        return False
    print(f"✅ Python {sys.version.split()[0]}")
    return True

def install_qemu_windows():
    """Installa QEMU su Windows."""
    print("🔧 Installazione QEMU per Windows...")
    
    # URL per QEMU Windows
    qemu_url = "https://qemu.weilnetz.de/w64/qemu-w64-setup-20231009.exe"
    
    print("💡 INSTALLAZIONE MANUALE RICHIESTA:")
    print(f"1. Scarica QEMU da: {qemu_url}")
    print("2. Installa seguendo le istruzioni")
    print("3. Aggiungi C:\\Program Files\\qemu al PATH")
    print("4. Riavvia il prompt dei comandi")
    
    # Verifica se già installato
    try:
        result = subprocess.run(['qemu-img', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ QEMU già installato!")
            return True
    except FileNotFoundError:
        pass
    
    print("\n⚠️  QEMU non trovato nel PATH")
    print("Dopo l'installazione, riavvia questo script")
    return False

def install_qemu_linux():
    """Installa QEMU su Linux."""
    print("🔧 Installazione QEMU per Linux...")
    
    # Prova diversi package manager
    commands = [
        ['sudo', 'apt-get', 'install', '-y', 'qemu-utils'],  # Ubuntu/Debian
        ['sudo', 'yum', 'install', '-y', 'qemu-img'],        # CentOS/RHEL
        ['sudo', 'dnf', 'install', '-y', 'qemu-img'],        # Fedora
        ['sudo', 'pacman', '-S', '--noconfirm', 'qemu'],     # Arch
    ]
    
    for cmd in commands:
        try:
            print(f"Tentativo: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print("✅ QEMU installato!")
                return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            continue
    
    print("❌ Installazione automatica fallita")
    print("💡 Installa manualmente: sudo apt-get install qemu-utils")
    return False

def install_python_packages():
    """Installa pacchetti Python necessari."""
    print("🐍 Installazione pacchetti Python...")
    
    packages = [
        'pathlib',  # Dovrebbe essere già incluso in Python 3.4+
    ]
    
    # Verifica moduli già disponibili
    available_modules = []
    for module in ['pathlib', 'json', 'hashlib', 'subprocess', 'os', 'sys']:
        try:
            __import__(module)
            available_modules.append(module)
        except ImportError:
            print(f"❌ Modulo mancante: {module}")
    
    print(f"✅ Moduli Python disponibili: {len(available_modules)}")
    return True

def create_batch_scripts():
    """Crea script batch per Windows."""
    if platform.system() != 'Windows':
        return
    
    print("📝 Creazione script batch...")
    
    # Script per estrarre salvataggi
    extract_bat = """@echo off
echo 🎮 XBOX SAVE EXTRACTOR
python xbox_save_tool.py
pause
"""
    
    with open('extract_saves.bat', 'w') as f:
        f.write(extract_bat)
    
    # Script per gestione completa
    manager_bat = """@echo off
echo 🔧 QCOW2 SAVE MANAGER
python qcow2_save_manager.py
pause
"""
    
    with open('save_manager.bat', 'w') as f:
        f.write(manager_bat)
    
    print("✅ Script batch creati:")
    print("  - extract_saves.bat")
    print("  - save_manager.bat")

def test_installation():
    """Testa l'installazione."""
    print("\n🧪 TEST INSTALLAZIONE")
    print("-" * 40)
    
    # Test qemu-img
    try:
        result = subprocess.run(['qemu-img', '--version'], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.split('\n')[0]
            print(f"✅ qemu-img: {version}")
        else:
            print("❌ qemu-img: errore")
            return False
    except FileNotFoundError:
        print("❌ qemu-img: non trovato")
        return False
    
    # Test Python modules
    required_modules = ['os', 'sys', 'json', 'pathlib', 'subprocess', 'hashlib']
    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ Python {module}: OK")
        except ImportError:
            print(f"❌ Python {module}: mancante")
            return False
    
    # Test creazione file temporaneo
    try:
        test_file = Path('test_temp.tmp')
        test_file.write_text('test')
        test_file.unlink()
        print("✅ Scrittura file: OK")
    except Exception as e:
        print(f"❌ Scrittura file: {e}")
        return False
    
    return True

def main():
    """Installazione principale."""
    print("🚀 INSTALLAZIONE DIPENDENZE XBOX SAVE TOOLS")
    print("=" * 60)
    
    # Verifica Python
    if not check_python_version():
        return False
    
    # Installa QEMU in base al sistema
    system = platform.system()
    print(f"🖥️  Sistema operativo: {system}")
    
    if system == 'Windows':
        qemu_ok = install_qemu_windows()
    elif system == 'Linux':
        qemu_ok = install_qemu_linux()
    else:
        print(f"❌ Sistema {system} non supportato automaticamente")
        print("💡 Installa QEMU manualmente")
        qemu_ok = False
    
    # Installa pacchetti Python
    python_ok = install_python_packages()
    
    # Crea script di utilità
    create_batch_scripts()
    
    # Test finale
    if qemu_ok and python_ok:
        print("\n🧪 Test installazione...")
        if test_installation():
            print("\n✅ INSTALLAZIONE COMPLETATA!")
            print("\n🎯 PROSSIMI PASSI:")
            print("1. Usa 'python xbox_save_tool.py' per operazioni semplici")
            print("2. Usa 'python qcow2_save_manager.py' per controllo avanzato")
            if system == 'Windows':
                print("3. Oppure usa i file .bat creati")
            
            print("\n📋 WORKFLOW CONSIGLIATO:")
            print("1. Estrai area salvataggi dall'HDD funzionante")
            print("2. Inietta l'area nell'HDD corrotto")
            print("3. Testa con xemu")
            
            return True
        else:
            print("\n❌ Test fallito - controlla gli errori sopra")
    else:
        print("\n❌ INSTALLAZIONE INCOMPLETA")
        if not qemu_ok:
            print("- QEMU non installato correttamente")
        if not python_ok:
            print("- Pacchetti Python mancanti")
    
    return False

if __name__ == "__main__":
    success = main()
    
    if not success:
        print("\n💡 RISOLUZIONE PROBLEMI:")
        print("- Riavvia come amministratore su Windows")
        print("- Verifica connessione internet")
        print("- Installa QEMU manualmente se necessario")
    
    input("\nPremi INVIO per uscire...")