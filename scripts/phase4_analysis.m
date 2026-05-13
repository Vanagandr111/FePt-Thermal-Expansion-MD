%% phase4_analysis.m
% Phase 4 — Fe₁₋ₓPtₓ MD Long Runs (50k eq + 100k prod)
% Lattice parameter analysis vs temperature and composition
% Output: 5 publication-ready figures + summary CSV
%
% Run from project root: C:\проекты\Nikolay\
%   >> cd C:\проекты\Nikolay
%   >> phase4_analysis
%
% Input:  output_v4/all_results.csv
% Output: output_v4/ (5 PNGs + phase4_summary.csv)
% ===========================================================================

clear; close all; clc;

%% Configuration
data_csv   = 'output_v4/all_results.csv';
output_dir = 'output_v4/';
if ~exist(output_dir, 'dir'), mkdir(output_dir); end

%% Load data
data = readtable(data_csv);
fprintf('Loaded %d rows from %s\n', height(data), data_csv);

% Column names used:
%   x_Pt, T_K, a_mean_Angstrom, a_std_Angstrom
x_Pt_vals = unique(data.x_Pt);
T_vals    = unique(data.T_K);
n_comp    = length(x_Pt_vals);
n_T       = length(T_vals);

%% Compute Δa = a_max - a_min for each composition
delta_a = zeros(n_comp, 1);
for i = 1:n_comp
    idx = data.x_Pt == x_Pt_vals(i);
    delta_a(i) = max(data.a_mean_Angstrom(idx)) - min(data.a_mean_Angstrom(idx));
end

%% Compute effective CTE α = Δa / a₀ / ΔT
alpha_eff = zeros(n_comp, 1);
for i = 1:n_comp
    idx  = data.x_Pt == x_Pt_vals(i);
    a0   = data.a_mean_Angstrom(idx & data.T_K == min(T_vals));
    aMax = data.a_mean_Angstrom(idx & data.T_K == max(T_vals));
    dT   = max(T_vals) - min(T_vals);
    alpha_eff(i) = (aMax - a0) / a0 / dT;
end

%% = Plot 1: a(T) — all compositions =======================================
figure; hold on; grid on;
markers = {'o', 's', '^', 'd', 'v'};
colors  = lines(n_comp);
for i = 1:n_comp
    idx = data.x_Pt == x_Pt_vals(i);
    errorbar(data.T_K(idx), data.a_mean_Angstrom(idx), data.a_std_Angstrom(idx), ...
        ['-' markers{i}], 'Color', colors(i,:), ...
        'LineWidth', 1.5, 'MarkerSize', 7, 'CapSize', 4, ...
        'DisplayName', sprintf('x_{Pt} = %.2f', x_Pt_vals(i)));
end
xlabel('T (K)'); ylabel('a ({\AA})');
title('Lattice parameter a(T) — Phase 4 Fe_{1-x}Pt_x');
legend('Location', 'northwest');
saveas(gcf, fullfile(output_dir, 'a_vs_T_all.png'));
fprintf('Saved: a_vs_T_all.png\n');

%% = Plot 2: a(T) — facets per composition =================================
ncols = 3; nrows = ceil(n_comp / ncols);
figure('Position', [100 100 1200 800]);
for i = 1:n_comp
    subplot(nrows, ncols, i); hold on; grid on;
    idx = data.x_Pt == x_Pt_vals(i);
    errorbar(data.T_K(idx), data.a_mean_Angstrom(idx), data.a_std_Angstrom(idx), ...
        '-o', 'LineWidth', 1.5, 'MarkerSize', 7, 'CapSize', 4, 'Color', colors(i,:));
    xlabel('T (K)'); ylabel('a ({\AA})');
    title(sprintf('x_{Pt}=%.2f, \\Delta a=%.4f{\\AA}', x_Pt_vals(i), delta_a(i)));
end
sgtitle('a(T) facets — Phase 4 Fe_{1-x}Pt_x');
saveas(gcf, fullfile(output_dir, 'a_vs_T_facets.png'));
fprintf('Saved: a_vs_T_facets.png\n');

%% = Plot 3: a(x_Pt) at fixed T ============================================
figure; hold on; grid on;
T_colors = jet(n_T);
for j = 1:n_T
    a_at_T = zeros(n_comp, 1);
    for i = 1:n_comp
        idx = data.x_Pt == x_Pt_vals(i) & data.T_K == T_vals(j);
        a_at_T(i) = data.a_mean_Angstrom(idx);
    end
    plot(x_Pt_vals, a_at_T, '-o', 'LineWidth', 1.5, ...
        'Color', T_colors(j,:), 'MarkerSize', 7, ...
        'DisplayName', sprintf('T = %d K', T_vals(j)));
end
xlabel('x_{Pt}'); ylabel('a ({\AA})');
title('a(x_{Pt}) at fixed T — Phase 4');
legend('Location', 'northwest');
saveas(gcf, fullfile(output_dir, 'a_vs_xPt.png'));
fprintf('Saved: a_vs_xPt.png\n');

%% = Plot 4: CTE vs x_Pt ==================================================
figure; hold on; grid on;
plot(x_Pt_vals, alpha_eff * 1e5, '-o', 'LineWidth', 2, ...
    'MarkerSize', 10, 'Color', [0.85 0.33 0.10], ...
    'MarkerFaceColor', 'w', 'MarkerEdgeColor', [0.85 0.33 0.10]);
for i = 1:n_comp
    text(x_Pt_vals(i), alpha_eff(i) * 1e5, ...
        sprintf('%.3f', alpha_eff(i) * 1e5), ...
        'HorizontalAlignment', 'center', 'VerticalAlignment', 'bottom', ...
        'FontSize', 10, 'FontWeight', 'bold');
end
xlabel('x_{Pt}'); ylabel('CTE \\alpha \\times 10^5 (K^{-1})');
title('Thermal expansion coefficient vs Pt fraction — Phase 4');
xlim([-0.05, 1.05]);
saveas(gcf, fullfile(output_dir, 'cte_vs_xPt.png'));
fprintf('Saved: cte_vs_xPt.png\n');

%% = Plot 5: Relative Δa/a₀ (%) ===========================================
figure; hold on; grid on;
a0 = zeros(n_comp, 1);
for i = 1:n_comp
    idx_comp = data.x_Pt == x_Pt_vals(i);
    a0(i)    = data.a_mean_Angstrom(idx_comp & data.T_K == min(T_vals));
end
for i = 1:n_comp
    idx_comp = data.x_Pt == x_Pt_vals(i);
    strain = zeros(n_T, 1);
    for j = 1:n_T
        idx = idx_comp & data.T_K == T_vals(j);
        strain(j) = (data.a_mean_Angstrom(idx) - a0(i)) / a0(i) * 100;
    end
    plot(T_vals, strain, ['-' markers{i}], 'Color', colors(i,:), ...
        'LineWidth', 1.5, 'MarkerSize', 7, ...
        'DisplayName', sprintf('x_{Pt}=%.2f', x_Pt_vals(i)));
end
xlabel('T (K)'); ylabel('\\Delta a / a_0 (%)');
title('Relative thermal expansion — Phase 4 Fe_{1-x}Pt_x');
legend('Location', 'northwest');
saveas(gcf, fullfile(output_dir, 'delta_a_percent.png'));
fprintf('Saved: delta_a_percent.png\n');

%% Summary CSV
summary_table = table(x_Pt_vals, delta_a, alpha_eff, ...
    'VariableNames', {'x_Pt', 'Delta_a_Angstrom', 'Alpha_eff_K-1'});
writetable(summary_table, fullfile(output_dir, 'phase4_summary.csv'));
fprintf('Saved: phase4_summary.csv\n');

%% Console summary
fprintf('\n======= Phase 4 Summary =======\n');
fprintf('%-8s %-12s %-14s\n', 'x_Pt', 'Δa (Å)', 'α_eff (K⁻¹)');
for i = 1:n_comp
    fprintf('%-8.2f %-12.4f %-14.2e\n', x_Pt_vals(i), delta_a(i), alpha_eff(i));
end
fprintf('================================\n');
disp('Phase 4 MATLAB analysis done.');
