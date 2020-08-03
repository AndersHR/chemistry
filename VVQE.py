from qiskit import QuantumRegister, ClassicalRegister, QuantumCircuit, execute
import numpy as np
from qiskit.chemistry.drivers import PySCFDriver, UnitsType, PyQuanteDriver
from qiskit.chemistry import FermionicOperator
from qiskit import BasicAer, Aer, execute
from qiskit.aqua.algorithms import  NumPyEigensolver
from scipy.optimize import minimize


from qiskit.chemistry.components.variational_forms import UCCSD
from qiskit.chemistry.components.initial_states import HartreeFock

import matplotlib.pyplot as plt
from matplotlib import rc
try:
    rc('text', usetex=True)
except:
    print("No LaTeX font available!")

newparams = {'figure.figsize': (10, 7), 'axes.grid': False,
             'lines.markersize': 10, 'lines.linewidth': 2,
             'font.size': 15, 'mathtext.fontset': 'stix',
             'font.family': 'STIXGeneral', 'figure.dpi': 200}
plt.rcParams.update(newparams)

# Atomic repulsion energy. In Hartree
SHIFT = 0.66147151365

#backend = Aer.get_backend("statevector_simulator")
backend = Aer.get_backend("qasm_simulator")

def create_VQE_circuit_RyRz_full_entangle_H2(params, depth=1):
    """
    Variational form where the number of CNots scales quadratic with number of qubits
    :param params: Array of 8 + 3 * 8 * depth elements
    :param depth:
    :return: quantum_circuit, quantum_register, classical_register of RyRz circuit
    """
    q = QuantumRegister(4)
    c = ClassicalRegister(4)
    qc = QuantumCircuit(q, c)
    qc.x(0)
    qc.x(1)
    counter = 0
    for d in range(depth):
        for k in range(3):
            for j in range(4):
                qc.ry(params[counter], j)
                counter += 1
            for j in range(4):
                qc.rz(params[counter], j)
                counter += 1
            qc.cx(0, 1)
            qc.cx(0, 2)
            qc.cx(0, 3)
            qc.cx(1, 2)
            qc.cx(1, 3)
            qc.cx(2, 3)
    for j in range(4):
        qc.ry(params[counter], j)
        counter += 1
    for j in range(4):
        qc.rz(params[counter], j)
        counter += 1
    return qc, q, c


def create_VQE_circuit_RyRz_linear_entangle_H2(params, depth=1):
    """
    Variational form where the number of CNots scales linearly with number of qubits
    :param params: Array of 8 + 3 * 8 * depth elements
    :param depth:
    :return: quantum_circuit, quantum_register, classical_register of RyRz circuit
    """
    q = QuantumRegister(4)
    c = ClassicalRegister(4)
    qc = QuantumCircuit(q,c)
    qc.x(0)
    qc.x(1)
    counter = 0
    for d in range(depth):
        for k in range(3):
            for j in range(4):
                qc.ry(params[counter], j)
                counter += 1
            for j in range(4):
                qc.rz(params[counter], j)
                counter += 1
            qc.cx(0, 1)
            qc.cx(1, 2)
            qc.cx(2, 3)
    for j in range(4):
        qc.ry(params[counter], j)
        counter += 1
    for j in range(4):
        qc.rz(params[counter], j)
        counter += 1
    return qc, q, c

def get_hamiltonian(distance, driver="pyquante"):
    if driver == "pyquante":
        driver = PyQuanteDriver(atoms="H .0 .0 .0; H .0 .0 " + str(distance), units=UnitsType.ANGSTROM, charge=0)
    else:
        driver = PySCFDriver(atom="H .0 .0 .0; H .0 .0 " + str(distance), unit=UnitsType.ANGSTROM,
                             charge=0, spin=0, basis='sto3g')
    molecule = driver.run()

    one_body = molecule.one_body_integrals
    two_body = molecule.two_body_integrals

    h = FermionicOperator(one_body, two_body)
    h = h.mapping("jordan_wigner")
    shift = molecule.nuclear_repulsion_energy
    return h, shift



def cost_function(params, alpha, backend, hamiltonian, shots=1000, depth=1, var_form="Full Entanglement"):
    if var_form=="Full Entanglement":
        qc, q, c = create_VQE_circuit_RyRz_full_entangle_H2(params, depth)
    # Implementation of q-UCCSD is a work in progress
    #elif var_form=="UCCSD":
    #    qc, q, c = get_VQE_UCCSD_circuit_H2(distance, params)
    else:
        qc, q, c = create_VQE_circuit_RyRz_linear_entangle_H2(params, depth)
    eval_circ_list = hamiltonian.construct_evaluation_circuit(wave_function=qc, statevector_mode=False, qr=q, cr=c)
    job = execute(eval_circ_list, backend, shots=shots)
    result = job.result()
    res = hamiltonian.evaluate_with_result(result=result, statevector_mode=False)
    mean = np.real(res[0])
    # res[1] is divided by sqrt(shots), thus the true variance must be scaled back
    std = np.real(res[1]) * np.sqrt(shots)
    return (1 - alpha) * mean + alpha * std


def find_optimal_params(method, init_params, alpha, hamiltonian, shots, depth=1, var_form="Full Entanglement"):
    optmize_result = minimize(cost_function, x0=init_params, method=method,
                              args=(alpha, backend, hamiltonian, shots, depth, var_form), options={"disp": False})#,"maxiter": 10})
    opt_params = optmize_result.x
    if var_form=="Full Entanglement":
        qc, q, c = create_VQE_circuit_RyRz_full_entangle_H2(opt_params, depth)
    #elif var_form=="UCCSD":
    #    qc, q, c = get_VQE_UCCSD_circuit_H2(distance, opt_params)
    elif var_form=="Linear Entanglement":
        qc, q, c = create_VQE_circuit_RyRz_linear_entangle_H2(opt_params, depth)
    eval_circ_list = hamiltonian.construct_evaluation_circuit(wave_function=qc, statevector_mode=False, qr=q, cr=c)
    job = execute(eval_circ_list, backend, shots=shots)
    result = job.result()
    res = hamiltonian.evaluate_with_result(result=result, statevector_mode=False)
    mean = np.real(res[0])
    error = np.real(res[1])
    return mean, error*np.sqrt(shots)

def simulate_variational_forms(alpha_list, distance, var_forms=["Full Entanglement", "UCCSD", "Linear Entanglement"], driver="pyquante"):
    """

    :param alpha_list: Array of alphas to simulate. M values
    :param distance:
    :param var_forms: Array of strings that specify the variational form to use. N values
    :param driver:
    :return: error_mean_matrix: (N,M) matrix. Each element is the deviance between the deviance between the calculated
            energy for a unique pair of var_form and alpha and the closest exact eigenenergy.
            std_matrix : (N, M) matrix. Each element is the standard deviance for a unique pair of var_form and alpha
            resulting from calculating the energy.
            excited_states_matrix: (N, M) matrix. Specifies which eigenenergy that is closest to the calculated energy
            for a unique alpha, var_form pair.
    """
    M = len(alpha_list)
    N = len(var_forms)
    h, shift = get_hamiltonian(distance, driver)
    result = NumPyEigensolver(h, k=9).run() # calculates k lowest eigengvalues
    energy_spectrum = np.real(result.eigenvalues)
    print(energy_spectrum + shift)
    error_mean_matrix = np.zeros((N, M))
    std_matrix = np.zeros((N, M))
    excited_states_matrix = np.zeros((N, M), dtype=np.int)
    for i in range(N):
        var_form = var_forms[i]
        print(var_form)
        if var_form=="UCCSD":
            init_params = np.ones(3)
        else:
            init_params = np.ones(32)
        for j in range(len(alpha_list)):
            print("Simulation number: ", j +1)
            mean, std = find_optimal_params("COBYLA", init_params, alpha_list[j], h, 1000, 1, var_form)
            print("Mean: ", mean + shift) # Adding the shift for convenience
            print("STD: ", std)
            print()
            temp_rec = 1000
            index = 0
            for k in range(len(energy_spectrum)):
                if np.abs(energy_spectrum[k] - mean) < temp_rec:
                    temp_rec = np.abs(energy_spectrum[k] - mean)
                    index = k
            error_mean_matrix[i,j] = temp_rec
            std_matrix[i,j] = std
            excited_states_matrix[i,j] = index
    error_mean_matrix = np.abs(error_mean_matrix)
    return error_mean_matrix, std_matrix, excited_states_matrix

def plot_results_var_forms(alpha_list, distance, error_mean_list, std_list, excited_states, var_forms = ["Full Entanglement", "UCCSD", "Linear Entanglement"]):
    cmap = plt.get_cmap('gnuplot')
    colors = [cmap(i) for i in np.linspace(0, 1, 9)]
    M = len(alpha_list)
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    unique_excited = np.unique(excited_states)
    for i in range(len(var_forms)):
        ax1.plot(alpha_list, std_list[i], label=var_forms[i])
        ax1.set_xlabel(r"$\alpha$")
        ax1.set_ylabel(r"$\sigma$")
        ax1.set_title(r"$\sigma$ for $H_2$ with bond length %0.2f Å" % distance)
        ax1.legend()
        for j in range(M):
            ax2.scatter(alpha_list[j], error_mean_list[i,j], color=colors[int(excited_states[i,j])])
        ax2.plot(alpha_list, error_mean_list[i], alpha=0.5, linestyle="-", label=var_forms[i])

    for j in range(len(unique_excited)):
        ax2.scatter(np.amin(alpha_list) - 10, np.amin(error_mean_list) + 10, color=colors[int(unique_excited[j])],
                    label=r'$k = $%0.0f' % unique_excited[j])
    ax2.set_xlim(min(np.amin(alpha_list) * 0.9, -0.1), np.amax(alpha_list) * 1.1)
    ax2.set_ylim(min(np.amin(alpha_list) * 0.9, -0.1), np.amax(error_mean_list)*1.1)
    ax2.set_xlabel(r"$\alpha$")
    ax2.set_ylabel(r"$|\mu - E_k|$")
    ax2.set_title(r"Deviance between $\mu$ and the closest eigenvalue $E_k$")
    ax2.legend()
    plt.show()

def find_effect_of_alpha(backend, var_form, alpha_list, distance, shots=1000, driver="pyquante", k=30):
    hamiltonian, shift = get_hamiltonian(distance, driver)
    energy_matrix = np.zeros((len(alpha_list), k))
    std_matrix = np.zeros((len(alpha_list), k))
    for i in range(len(alpha_list)):
        for j in range(k):
            optmize_result = minimize(cost_function, x0=np.zeros(32), method="COBYLA",
                                      args=(alpha_list[i], backend, hamiltonian, shots, 1, var_form),
                                      options={"disp": False})
            opt_params = optmize_result.x
            if var_form == "Full Entanglement":
                qc, q, c = create_VQE_circuit_RyRz_full_entangle_H2(opt_params, 1)
            elif var_form == "Linear Entanglement":
                qc, q, c = create_VQE_circuit_RyRz_linear_entangle_H2(opt_params, 1)
            eval_circ_list = hamiltonian.construct_evaluation_circuit(wave_function=qc, statevector_mode=False, qr=q, cr=c)
            job = execute(eval_circ_list, backend, shots=shots)
            result = job.result()
            res = hamiltonian.evaluate_with_result(result=result, statevector_mode=False)
            mean = np.real(res[0])
            error = np.real(res[1])
            std = np.sqrt(shots) * error
            print(j, " alpha : ", alpha_list[i])
            print("Mean: ", mean + shift)
            print("std: ", std)
            energy_matrix[i, j] = mean
            std_matrix[i, j] = std
    return energy_matrix, std_matrix, shift


def plot_effects_of_alpha(alpha_list, energy_matrix, std_matrix, shift):
    fig, ax = plt.subplots(len(alpha_list), 1, sharex=True)
    big, bx = plt.subplots(len(alpha_list), 1, sharex=True)

    for i in range(np.shape(energy_matrix)[0]):
        n, bins, patches = ax[i].hist(x=energy_matrix[i]+ shift, bins='auto', color='#0504aa',
                                    alpha=0.5, rwidth=0.85)
        ax[i].set_title(r"$\alpha = $ %0.2f" % alpha_list[i])
        ax[i].set_ylabel('Freq.')
        maxfreq = n.max()
        ax[i].set_ylim(ymax=np.ceil(maxfreq / 10) * 10 if maxfreq % 10 else maxfreq + 10)
        ax[i].axvline(np.mean(energy_matrix[i]+ shift), 0, maxfreq, color="k")

        n, bins, patches = bx[i].hist(x=std_matrix[i], bins='auto', color='#0504aa',
                                    alpha=0.7, rwidth=0.85)
        bx[i].set_ylabel('Frequency')
        bx[i].set_title(r"$\alpha = $ %0.2f" % alpha_list[i])
        bx[i].axvline(np.mean(std_matrix[i]), 0, maxfreq, color="k")
        maxfreq_std = n.max()
        # Set a clean upper y-axis limit.
        bx[i].set_ylim(ymax=np.ceil(maxfreq_std / 10) * 10 if maxfreq_std % 10 else maxfreq_std + 10)
    ax[-1].set_xlabel(r'$\mu$')
    bx[-1].set_xlabel(r"$\sigma$")

    ax[-1].axvline(np.mean(energy_matrix[-1]) + shift, 0, maxfreq, color="k", label="Mean")
    bx[-1].axvline(np.mean(std_matrix[-1]), 0, maxfreq, color="k", label="Mean")

    fig.legend()
    big.legend()
    fig.tight_layout()
    big.tight_layout()
    plt.show()


M = 4
distance = 0.8

#var_forms = ["Full Entanglement", "Linear Entanglement"]
#error_mean_list, std_list, excited_states = simulate_variational_forms(alpha_list, distance, var_forms)
#plot_results_var_forms(alpha_list, distance, error_mean_list, std_list, excited_states, var_forms)

# Full entanglement, small alphas
alpha_list1 = np.genfromtxt("data_VVQE/alpha_list1.csv", delimiter=",")
energy_matrix1 = np.genfromtxt("data_VVQE/energy_matrix1.csv", delimiter=",")
std_matrix1 = np.genfromtxt("data_VVQE/std_matrix1.csv", delimiter=",")

# Full entanglement, larger alphas
alpha_list2 = np.genfromtxt("data_VVQE/alpha_list2.csv", delimiter=",")
energy_matrix2 = np.genfromtxt("data_VVQE/energy_matrix2.csv", delimiter=",")
std_matrix2 = np.genfromtxt("data_VVQE/std_matrix2.csv", delimiter=",")

# Linear entanglement, smaller alphas
alpha_list3 = np.genfromtxt("data_VVQE/alpha_list3.csv", delimiter=",")
energy_matrix3 = np.genfromtxt("data_VVQE/energy_matrix3.csv", delimiter=",")
std_matrix3 = np.genfromtxt("data_VVQE/std_matrix3.csv", delimiter=",")

# Linear entanglement, larger alphas
alpha_list4 = np.genfromtxt("data_VVQE/alpha_list4.csv", delimiter=",")
energy_matrix4 = np.genfromtxt("data_VVQE/energy_matrix4.csv", delimiter=",")
std_matrix4 = np.genfromtxt("data_VVQE/std_matrix4.csv", delimiter=",")

plot_effects_of_alpha(alpha_list1, energy_matrix1, std_matrix1, SHIFT)
plot_effects_of_alpha(alpha_list2, energy_matrix2, std_matrix2, SHIFT)
plot_effects_of_alpha(alpha_list3, energy_matrix3, std_matrix3, SHIFT)
plot_effects_of_alpha(alpha_list4, energy_matrix4, std_matrix4, SHIFT)


